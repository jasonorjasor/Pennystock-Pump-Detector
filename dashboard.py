# dashboard.py
import os
import glob
import pandas as pd
import numpy as np
import streamlit as st
import altair as alt
from datetime import datetime

# ---------------------------
# Helpers
# ---------------------------
def find_latest_run():
    candidates = [
        d for d in glob.glob("runs/*/")
        if os.path.isdir(d) and os.path.basename(os.path.normpath(d)) != "LATEST"
    ]
    if not candidates:
        st.error("No run directories found under runs/. Run your pipeline first.")
        st.stop()
    return max(candidates, key=os.path.getmtime)

@st.cache_data
def load_alert_history(run_dir: str):
    alerts_path = os.path.join(run_dir, "data", "alerts", "alerts_history.csv")
    if not os.path.exists(alerts_path):
        st.error(f"alerts_history.csv not found at: {alerts_path}")
        st.stop()
    df = pd.read_csv(alerts_path)
    # Normalize/parse expected columns
    if "alert_date" in df.columns:
        df["alert_date"] = pd.to_datetime(df["alert_date"], errors="coerce")
    # Safety: coerce numerics
    for col in ["pump_score", "alert_price", "vol_z", "daily_return", "days_since_last"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # Fill missing standard fields if absent (won't break visuals)
    for col in ["ticker", "tier", "status", "outcome"]:
        if col not in df.columns:
            df[col] = np.nan
    return df

def compute_precision(df: pd.DataFrame):
    # Precision = (confirmed_pump + likely_pump) / classified
    classified = df[df["outcome"].isin(["confirmed_pump", "likely_pump", "false_positive", "uncertain"])]
    if len(classified) == 0:
        return np.nan, 0
    pumps = classified["outcome"].isin(["confirmed_pump", "likely_pump"]).sum()
    precision = pumps / len(classified)
    return precision, len(classified)

# ---------------------------
# App
# ---------------------------
st.set_page_config(page_title="Pump Detector Dashboard", layout="wide")
st.title("Pump-and-Dump Detector — Live Alerts Dashboard")

run_dir = find_latest_run()
st.caption(f"Using latest run: {os.path.normpath(run_dir)}")

df = load_alert_history(run_dir)

# Sidebar filters
st.sidebar.header("Filters")
tickers = sorted([t for t in df["ticker"].dropna().unique()])
tiers   = sorted([t for t in df["tier"].dropna().unique()])
outcomes = ["confirmed_pump", "likely_pump", "uncertain", "false_positive", "pending"]

sel_tickers = st.sidebar.multiselect("Ticker", tickers, default=tickers[:10] if tickers else [])
sel_tiers   = st.sidebar.multiselect("Tier", tiers, default=tiers if tiers else [])
sel_outcomes = st.sidebar.multiselect("Outcome", outcomes, default=outcomes)

date_min = df["alert_date"].min()
date_max = df["alert_date"].max()
if pd.isna(date_min) or pd.isna(date_max):
    date_range = (None, None)
else:
    date_range = st.sidebar.date_input("Date range", value=(date_min.date(), date_max.date()))

# Apply filters
filt = df.copy()
if sel_tickers:
    filt = filt[filt["ticker"].isin(sel_tickers)]
if sel_tiers:
    filt = filt[filt["tier"].isin(sel_tiers)]
if sel_outcomes:
    filt = filt[filt["outcome"].isin(sel_outcomes)]
if date_range and all(date_range):
    start_dt = datetime.combine(date_range[0], datetime.min.time())
    end_dt   = datetime.combine(date_range[1], datetime.max.time())
    if "alert_date" in filt.columns:
        filt = filt[(filt["alert_date"] >= start_dt) & (filt["alert_date"] <= end_dt)]

st.subheader("Key Metrics")

col1, col2, col3, col4 = st.columns(4)
with col1:
    total_alerts = len(filt)
    st.metric("Total Alerts (filtered)", total_alerts)
with col2:
    precision, classified_n = compute_precision(filt)
    st.metric("Precision (filtered)", f"{precision*100:.1f}%" if not np.isnan(precision) else "N/A")
with col3:
    tier_counts = filt["tier"].value_counts()
    top_tier = tier_counts.idxmax() if len(tier_counts) else "N/A"
    st.metric("Most Active Tier", f"{top_tier}")
with col4:
    avg_score = filt["pump_score"].mean() if "pump_score" in filt.columns else np.nan
    st.metric("Avg Pump Score", f"{avg_score:.1f}" if not np.isnan(avg_score) else "N/A")

st.divider()

# Charts
st.subheader("Alerts Over Time")
if "alert_date" in filt.columns and len(filt) > 0:
    daily = (
        filt.dropna(subset=["alert_date"])
            .groupby(filt["alert_date"].dt.date)
            .size()
            .reset_index(name="alerts")
            .rename(columns={"alert_date": "date"})
    )
    line = alt.Chart(daily).mark_line(point=True).encode(
        x=alt.X("date:T", title="Date"),
        y=alt.Y("alerts:Q", title="Alerts"),
        tooltip=["date:T", "alerts:Q"]
    ).properties(height=250)
    st.altair_chart(line, use_container_width=True)
else:
    st.info("No alert dates found to plot.")

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Outcome Distribution")
    if "outcome" in filt.columns and len(filt) > 0:
        counts = (
            filt["outcome"]
            .value_counts(dropna=False)
            .rename_axis("outcome")
            .reset_index(name="count")
        )
        bar = alt.Chart(counts).mark_bar().encode(
            x=alt.X("outcome:N", sort="-y", title="Outcome"),
            y=alt.Y("count:Q", title="Count"),
            tooltip=["outcome:N", "count:Q"]
        ).properties(height=250)
        st.altair_chart(bar, use_container_width=True)
    else:
        st.info("No outcomes to display.")

with col_b:
    st.subheader("Average Score by Ticker (Top 15)")
    if "ticker" in filt.columns and "pump_score" in filt.columns and len(filt) > 0:
        top = (
            filt.groupby("ticker")["pump_score"]
            .mean()
            .reset_index()
            .sort_values("pump_score", ascending=False)
            .head(15)
        )
        bar2 = alt.Chart(top).mark_bar().encode(
            x=alt.X("pump_score:Q", title="Avg Pump Score"),
            y=alt.Y("ticker:N", sort="-x", title="Ticker"),
            tooltip=["ticker:N", alt.Tooltip("pump_score:Q", format=".1f")]
        ).properties(height=250)
        st.altair_chart(bar2, use_container_width=True)
    else:
        st.info("No score data available.")

st.divider()

st.subheader("Recent Alerts")
# Order by most recent
if "alert_date" in filt.columns and len(filt) > 0:
    show_cols = [
        c for c in [
            "alert_date", "ticker", "tier", "pump_score", "alert_price",
            "vol_z", "daily_return", "status", "days_since_last", "outcome"
        ] if c in filt.columns
    ]
    st.dataframe(
        filt.sort_values("alert_date", ascending=False)[show_cols].head(200),
        use_container_width=True
    )
else:
    st.info("No alerts to display.")

st.caption("Tip: As your tracker updates outcomes over 1–2 weeks, this dashboard will reflect live precision and per-ticker performance automatically.")
