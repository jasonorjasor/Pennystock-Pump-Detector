# dashboard.py
import os
from pathlib import Path
from datetime import timedelta

import pandas as pd
import streamlit as st
import yfinance as yf
import altair as alt

# ----------------------------
# Streamlit config
# ----------------------------
st.set_page_config(page_title="Pump-and-Dump Detector — Live Alerts", layout="wide")
st.title("Pump-and-Dump Detector — Live Alerts Dashboard")

# ----------------------------
# Runs root discovery
# ----------------------------
def discover_runs_root() -> Path:
    """
    Find the 'runs' directory robustly, whether this file is in project root or a subfolder.
    Priority:
      1) RUNS_ROOT env var
      2) <project_root>/runs near this file (walk up to 5 levels)
    """
    env = os.getenv("RUNS_ROOT")
    if env:
        p = Path(env).expanduser().resolve()
        if p.exists() and p.is_dir():
            return p

    here = Path(__file__).resolve()
    candidates = [
        here.parent / "runs",
        here.parent.parent / "runs",
        here.parent.parent.parent / "runs",
    ]
    for c in candidates:
        if c.exists() and c.is_dir() and any(c.glob("*/")):
            return c

    cur = here.parent
    for _ in range(5):
        maybe = cur / "runs"
        if maybe.exists() and maybe.is_dir() and any(maybe.glob("*/")):
            return maybe
        cur = cur.parent
    return None

RUNS_ROOT = discover_runs_root()
if RUNS_ROOT is None:
    st.error("Could not locate a 'runs' directory. Set RUNS_ROOT or ensure a runs/ folder exists.")
    st.stop()

# ----------------------------
# Helpers: find runs + load alerts
# ----------------------------
def list_run_dirs(root: Path):
    candidates = [
        d for d in root.glob("*/")
        if d.is_dir() and d.name.upper() != "LATEST"
    ]
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)

def alerts_path(run_dir: Path):
    return run_dir / "data" / "alerts" / "alerts_history.csv"

@st.cache_data(show_spinner=False)
def try_load_alerts(run_dir: Path):
    path = alerts_path(run_dir)
    if not path.exists():
        return None, str(path)

    df = pd.read_csv(path)

    # Normalize likely date columns
    for c in [c for c in ["alert_date", "date"] if c in df.columns]:
        df[c] = pd.to_datetime(df[c], errors="coerce")

    # Normalize string-ish columns
    for c in ["ticker", "tier", "outcome", "status"]:
        if c in df.columns:
            df[c] = df[c].astype(str)

    return df, str(path)

@st.cache_data(show_spinner=False)
def load_price(ticker: str, start, end):

    try:
        # First attempt: bounded download
        df1 = yf.download(ticker, start=start, end=end, interval="1d", progress=False)
        if df1 is not None and not df1.empty:
            out = df1.rename_axis("date").reset_index()[["date","Close"]].rename(columns={"Close":"close"})
            return out

        # Fallback: full history then slice
        tk = yf.Ticker(ticker)
        df2 = tk.history(period="max", interval="1d", auto_adjust=False)
        if df2 is not None and not df2.empty:
            df2 = df2.rename_axis("date").reset_index()
            df2 = df2[(df2["date"].dt.date >= start) & (df2["date"].dt.date <= end)]
            if not df2.empty:
                return df2[["date","Close"]].rename(columns={"Close":"close"})
    except Exception as e:
        # Surface error to caller
        return pd.DataFrame({"__error__":[str(e)]})

    # Nothing worked
    return pd.DataFrame()


def is_pump_series(s: pd.Series) -> pd.Series:
    return s.astype(str).isin(["confirmed_pump", "likely_pump"])

def style_outcome(df_show: pd.DataFrame) -> "pd.io.formats.style.Styler":
    colors = {
        "confirmed_pump": "#22c55e",   # green
        "likely_pump":    "#86efac",   # light green
        "false_positive": "#ef4444",   # red
        "uncertain":      "#f59e0b",   # amber
        "pending":        "#cbd5e1",   # slate
    }
    def highlight(row):
        c = colors.get(str(row.get("outcome", "")), None)
        return [f"background-color: {c}; color: black" if c else "" for _ in row]
    return df_show.style.apply(highlight, axis=1)

# ----------------------------
# Load run
# ----------------------------
runs = list_run_dirs(RUNS_ROOT)
if not runs:
    st.error(f"No runs found under {RUNS_ROOT}/.")
    st.stop()

sel_run = st.sidebar.selectbox(
    "Select run",
    options=runs,
    index=0,
    format_func=lambda p: str(p.relative_to(RUNS_ROOT))
)

df, csv_path = try_load_alerts(sel_run)
st.caption(f"Using latest run: {csv_path.replace('/', os.sep)}")

if df is None or df.empty:
    st.warning("No alerts_history.csv for this run (or file is empty). Run your scanner.")
    st.stop()

# ----------------------------
# Sidebar filters
# ----------------------------
with st.sidebar:
    st.subheader("Filters")

    DATE_COL = "alert_date" if "alert_date" in df.columns else ("date" if "date" in df.columns else None)

    if "tier" in df.columns:
        tiers = sorted([t for t in df["tier"].dropna().unique()])
        sel_tiers = st.multiselect("Tier", tiers, default=tiers)
    else:
        tiers, sel_tiers = [], []

    if "outcome" in df.columns:
        outcomes = sorted([o for o in df["outcome"].dropna().unique()])
        sel_outcomes = st.multiselect("Outcome", outcomes, default=outcomes)
    else:
        outcomes, sel_outcomes = [], []

# Apply filters
fdf = df.copy()
if sel_tiers:
    fdf = fdf[fdf["tier"].isin(sel_tiers)]
if sel_outcomes:
    fdf = fdf[fdf["outcome"].isin(sel_outcomes)]

# ----------------------------
# KPI Tiles
# ----------------------------
st.subheader("Key Metrics")

total_alerts = len(fdf)
classified_mask = fdf["outcome"].astype(str).isin(
    ["confirmed_pump", "likely_pump", "false_positive", "uncertain"]
) if "outcome" in fdf.columns else pd.Series(False, index=fdf.index)
classified = fdf[classified_mask]
precision = None
if not classified.empty and "outcome" in classified.columns:
    pumps = is_pump_series(classified["outcome"]).sum()
    precision = 100.0 * pumps / len(classified)

most_active_tier = fdf["tier"].value_counts().idxmax() if "tier" in fdf.columns and not fdf.empty else "—"
avg_score = fdf["pump_score"].mean() if "pump_score" in fdf.columns and not fdf.empty else None

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Alerts (filtered)", f"{total_alerts}")
c2.metric("Precision (filtered)", f"{precision:.1f}%" if precision is not None else "N/A")
c3.metric("Most Active Tier", f"{most_active_tier}")
c4.metric("Avg Pump Score", f"{avg_score:.1f}" if avg_score is not None else "—")

# ----------------------------
# Alerts Over Time (line)
# ----------------------------
if DATE_COL:
    tmp_count = fdf[[DATE_COL]].dropna().copy()
    tmp_count["d"] = tmp_count[DATE_COL].dt.to_period("D").dt.start_time
    by_day = tmp_count.groupby("d").size().reset_index(name="alerts")
    st.subheader("Alerts Over Time")
    if not by_day.empty:
        st.line_chart(by_day.set_index("d")["alerts"])
    else:
        st.caption("No dates available to plot.")

# ----------------------------
# Outcome Distribution (bar)
# ----------------------------
st.subheader("Outcome Distribution")
if "outcome" in fdf.columns and not fdf.empty:
    out_counts = fdf["outcome"].value_counts().reset_index()
    out_counts.columns = ["Outcome", "Count"]
    chart_out = alt.Chart(out_counts).mark_bar().encode(
        x=alt.X("Outcome:N", sort="-y"),
        y=alt.Y("Count:Q")
    ).properties(height=280)
    st.altair_chart(chart_out, use_container_width=True)
else:
    st.caption("No outcome column to chart yet.")

# ----------------------------
# Average Score by Ticker (Top 15)
# ----------------------------
st.subheader("Average Score by Ticker (Top 15)")
if "pump_score" in fdf.columns and "ticker" in fdf.columns and not fdf.empty:
    avg_by_ticker = (
        fdf.groupby("ticker")["pump_score"]
        .mean()
        .reset_index(name="avg_score")
        .sort_values("avg_score", ascending=False)
        .head(15)
    )
    if not avg_by_ticker.empty:
        chart_score = alt.Chart(avg_by_ticker).mark_bar().encode(
            x=alt.X("avg_score:Q", title="Avg Pump Score"),
            y=alt.Y("ticker:N", sort="-x", title="Ticker")
        ).properties(height=320)
        st.altair_chart(chart_score, use_container_width=True)
    else:
        st.caption("No scores to chart.")
else:
    st.caption("Need columns: ticker, pump_score.")

# ----------------------------
# Summary by ticker
# ----------------------------
st.subheader("Alert Summary by Ticker")
if not fdf.empty and "ticker" in fdf.columns:
    agg = {"ticker": ("ticker", "count")}
    if "pump_score" in fdf.columns:
        agg["avg_score"] = ("pump_score", "mean")

    if "outcome" in fdf.columns:
        agg["pumps"] = ("outcome", lambda s: is_pump_series(s).sum())

    grp = fdf.groupby("ticker").agg(**agg).rename(columns={"ticker": "alerts"})
    if "avg_score" in grp.columns:
        grp["avg_score"] = grp["avg_score"].round(2)
    if "pumps" in grp.columns:
        grp["precision_%"] = (100.0 * grp["pumps"] / grp["alerts"]).round(2)
    st.dataframe(grp.sort_values("alerts", ascending=False), use_container_width=True)
else:
    st.info("No rows after filters.")

# ----------------------------
# Recent Alerts (table + download)
# ----------------------------
st.subheader("Recent Alerts")
candidate_cols = [
    "alert_date", "date", "ticker", "tier", "pump_score",
    "status", "outcome", "alert_price", "vol_z", "daily_return"
]
show_cols = [c for c in candidate_cols if c in fdf.columns]
fdf_sorted = fdf.sort_values(DATE_COL, ascending=False) if DATE_COL else fdf.copy()
table_recent = fdf_sorted[show_cols].head(300)

try:
    st.dataframe(style_outcome(table_recent), use_container_width=True)
except Exception:
    st.dataframe(table_recent, use_container_width=True)

st.download_button(
    label="Download filtered alerts (CSV)",
    data=table_recent.to_csv(index=False).encode("utf-8"),
    file_name="filtered_alerts.csv",
    mime="text/csv",
)

# ----------------------------
# Ticker Detail (robust)
# ----------------------------
# Sidebar selector (auto-picks first ticker so something shows)
tickers = sorted(fdf["ticker"].dropna().unique()) if "ticker" in fdf.columns else []
default_idx = 1 if tickers else 0  # 0="(none)", 1=first ticker
sel_ticker = st.sidebar.selectbox("Ticker detail", options=["(none)"] + tickers, index=default_idx)

st.subheader("Ticker Detail")
if sel_ticker and sel_ticker != "(none)":
    if "ticker" not in fdf.columns:
        st.info("No ticker column available.")
    else:
        tdf = fdf[fdf["ticker"] == sel_ticker].copy()
        DATE_COL_T = "alert_date" if "alert_date" in tdf.columns else ("date" if "date" in tdf.columns else None)

        left, right = st.columns([2, 1])
        with left:
            view_cols = [c for c in ["alert_date","date","tier","pump_score","outcome","daily_return","alert_price","vol_z"] if c in tdf.columns]
            table_ticker = (tdf.sort_values(DATE_COL_T, ascending=False)[view_cols] if DATE_COL_T else tdf[view_cols])
            st.write(f"**{sel_ticker} — {len(tdf)} alerts**")
            try:
                st.dataframe(style_outcome(table_ticker), use_container_width=True)
            except Exception:
                st.dataframe(table_ticker, use_container_width=True)

        with right:
            if "outcome" in tdf.columns and len(tdf) > 0:
                pumps = tdf["outcome"].astype(str).isin(["confirmed_pump","likely_pump"]).sum()
                prec = 100.0 * pumps / len(tdf) if len(tdf) else 0.0
                st.metric("Precision (this ticker)", f"{prec:.1f}%")
            if "pump_score" in tdf.columns and len(tdf) > 0:
                st.metric("Avg pump_score", f"{tdf['pump_score'].mean():.1f}")

        # --- Choose a wide window so Yahoo is more likely to return data
        if DATE_COL_T and not tdf[DATE_COL_T].isna().all():
            dmin = pd.to_datetime(tdf[DATE_COL_T].min())
            dmax = pd.to_datetime(tdf[DATE_COL_T].max())
            start = (dmin - timedelta(days=90)).date()
            end   = (dmax + timedelta(days=120)).date()
        else:
            end = pd.Timestamp.today().date()
            start = (pd.Timestamp.today() - pd.Timedelta(days=240)).date()

        # --- Load price with diagnostics
        price = load_price(sel_ticker, start=start, end=end)

        st.markdown("**Price chart (with alert markers)**")
        # Diagnostic panel (collapsible) to help if chart doesn't appear
        with st.expander("Debug (price fetch details)"):
            st.write({"ticker": sel_ticker, "start": str(start), "end": str(end)})
            if isinstance(price, pd.DataFrame) and "__error__" in price.columns:
                st.error(f"yfinance error: {price['__error__'].iloc[0]}")
            else:
                st.write("price rows:", 0 if price is None else len(price))

        # --- Plot logic
        if price is None or (isinstance(price, pd.DataFrame) and price.empty) or ("close" not in price.columns):
            # Fallback: show alert-day returns if available
            alt_df = tdf.copy()
            if "daily_return" in alt_df.columns and not alt_df["daily_return"].isna().all():
                st.caption("No Yahoo price data — showing alert-day returns instead.")
                tmp = alt_df[[DATE_COL_T,"daily_return"]].dropna().rename(columns={DATE_COL_T:"date"})
                tmp = tmp.sort_values("date")
                st.line_chart(tmp.set_index("date")["daily_return"])
            else:
                st.info("No price data available.")
        else:
            # Use Altair with red vertical alert lines
            import altair as alt
            price_reset = price.copy()
            # ensure 'date' is datetime for Altair
            price_reset["date"] = pd.to_datetime(price_reset["date"])
            line = (
                alt.Chart(price_reset)
                .mark_line()
                .encode(
                    x=alt.X("date:T", title="Date"),
                    y=alt.Y("close:Q", title="Close")
                )
                .properties(height=260, width="container")
            )

            rule_df = pd.DataFrame({"date": []})
            if DATE_COL_T:
                rule_df = pd.DataFrame({
                    "date": sorted(pd.to_datetime(tdf[DATE_COL_T].dropna()).dt.normalize().unique())
                })
            rules = alt.Chart(rule_df).mark_rule(color="red", opacity=0.5).encode(x="date:T")
            st.altair_chart(line + rules, use_container_width=True)

            if DATE_COL_T and not rule_df.empty:
                alert_dates = sorted(pd.to_datetime(tdf[DATE_COL_T].dropna()).dt.date.unique())
                st.caption("Alert dates: " + ", ".join(str(d) for d in alert_dates[:20]) + (" …" if len(alert_dates) > 20 else ""))
else:
    st.caption("Pick a ticker in the sidebar to see details.")

# ----------------------------
# Performance Visuals: Precision by Tier + Weekly Precision
# ----------------------------
st.subheader("Performance Visuals")

# Precision by tier (bar)
if "tier" in fdf.columns and "outcome" in fdf.columns and not fdf.empty:
    by_tier = (
        fdf.groupby("tier")["outcome"]
        .apply(lambda s: (is_pump_series(s).mean()) * 100.0)
        .reset_index(name="precision_pct")
        .sort_values("precision_pct", ascending=False)
    )
    if not by_tier.empty:
        chart_tier = alt.Chart(by_tier).mark_bar().encode(
            x=alt.X("tier:N", title="Tier"),
            y=alt.Y("precision_pct:Q", title="Precision (%)")
        ).properties(height=300)
        st.altair_chart(chart_tier, use_container_width=True)

# Weekly precision over time (line)
if DATE_COL and "outcome" in fdf.columns:
    tmp = fdf[[DATE_COL, "outcome"]].dropna().copy()
    if not tmp.empty:
        tmp["week"] = tmp[DATE_COL].dt.to_period("W").dt.start_time
        weekly = (
            tmp.groupby("week")["outcome"]
            .apply(lambda s: (is_pump_series(s).mean()) * 100.0)
            .reset_index(name="precision_pct")
            .sort_values("week")
        )
        if not weekly.empty:
            chart_week = alt.Chart(weekly).mark_line().encode(
                x=alt.X("week:T", title="Week"),
                y=alt.Y("precision_pct:Q", title="Precision (%)")
            ).properties(height=300)
            st.altair_chart(chart_week, use_container_width=True)
