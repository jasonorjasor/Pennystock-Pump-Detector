"""Shared, deterministic market features, outcomes, universes, and metrics."""
from math import sqrt
import numpy as np
import pandas as pd
from . import SCORE_VERSION, OUTCOME_VERSION, THRESHOLD

OHLCV = ["Open", "High", "Low", "Close", "Volume"]
FEATURES = ["vol_z", "vol_ratio", "vol_trend", "return", "price_z", "gap_up", "volatility"]
RULES = [
    ("volume_z_2", "vol_z", 2, 20), ("volume_z_3", "vol_z", 3, 10),
    ("relative_volume", "vol_ratio", 3, 15), ("return_10pct", "return", .10, 20),
    ("return_20pct", "return", .20, 10), ("return_z", "price_z", 2, 15),
    ("gap_5pct", "gap_up", .05, 10), ("range_10pct", "volatility", .10, 10),
]


def normalize_bars(raw, ticker=None):
    if raw is None or raw.empty:
        return pd.DataFrame(columns=OHLCV, index=pd.DatetimeIndex([], name="Date"))
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        field_levels = [i for i in range(df.columns.nlevels)
                        if set(OHLCV).issubset(set(df.columns.get_level_values(i)))]
        if len(field_levels) != 1:
            raise ValueError("Cannot identify OHLCV column level")
        field_level = field_levels[0]
        if df.columns.nlevels != 2:
            raise ValueError("Expected two column levels")
        other = 1 - field_level
        names = df.columns.get_level_values(other).unique()
        selected = ticker if ticker in names else (names[0] if ticker is None and len(names) == 1 else None)
        if selected is None:
            raise ValueError(f"Ticker {ticker} absent from batch")
        df = df.xs(selected, axis=1, level=other)
    if not isinstance(df.index, pd.DatetimeIndex):
        date_col = next((c for c in ["Date", "date", "Datetime"] if c in df), None)
        if date_col is None:
            raise ValueError("Bars require dates")
        df = df.set_index(date_col)
    df.index = pd.DatetimeIndex(pd.to_datetime(df.index))
    if df.index.tz is not None:
        df.index = df.index.tz_convert("America/New_York").tz_localize(None)
    df.index = df.index.normalize()
    df.index.name = "Date"
    if df.index.has_duplicates or df.index.hasnans:
        raise ValueError("Duplicate or invalid bar dates")
    if not set(OHLCV).issubset(df.columns):
        raise ValueError("Missing OHLCV columns")
    df[OHLCV] = df[OHLCV].apply(pd.to_numeric, errors="coerce")
    return df.sort_index().replace([np.inf, -np.inf], np.nan)


def valid_bars(df):
    return (df[OHLCV].notna().all(axis=1) & df[OHLCV[:4]].gt(0).all(axis=1)
            & df.Volume.gt(0) & df.High.ge(df[["Open", "Close", "Low"]].max(axis=1))
            & df.Low.le(df[["Open", "Close", "High"]].min(axis=1)))


def calculate_pump_score(bars):
    """Prior-session baselines; no invented prices or volume. Maximum: 130 points."""
    df = bars.copy()
    valid = valid_bars(df)
    prices = df[OHLCV].where(valid)
    volume = prices.Volume
    mean = volume.shift(1).rolling(20).mean()
    df["vol_z"] = (volume - mean) / (volume.shift(1).rolling(20).std() + 1e-9)
    df["vol_ratio"] = volume / (mean + 1e-9)
    df["vol_trend"] = volume.rolling(5).mean() / (mean + 1e-9)
    df["return"] = prices.Close.pct_change(fill_method=None)
    df["price_z"] = (df["return"] - df["return"].shift(1).rolling(20).mean()) / (
        df["return"].shift(1).rolling(20).std() + 1e-9)
    df["gap_up"] = prices.Open / prices.Close.shift(1) - 1
    df["volatility"] = (prices.High - prices.Low) / prices.Close
    df["eligible"] = valid & df[FEATURES].notna().all(axis=1) & df["return"].abs().le(5)
    columns = []
    for name, feature, cutoff, points in RULES:
        col = "points_" + name
        df[col] = ((df[feature] > cutoff) & df.eligible).astype(int) * points
        columns.append(col)
    df["points_volume_acceleration"] = ((df.vol_trend > 1.2) & (df["return"] > .1) & df.eligible).astype(int) * 10
    df["points_joint_anomaly"] = ((df.price_z > 2.5) & (df.vol_ratio > 2) & df.eligible).astype(int) * 10
    columns += ["points_volume_acceleration", "points_joint_anomaly"]
    df["pump_score"] = df[columns].sum(axis=1)
    df["flag"] = df.eligible & df.pump_score.gt(THRESHOLD)
    df["score_version"] = SCORE_VERSION
    return df


def explain(row):
    result = [{"rule": name, "feature": feature, "value": float(row[feature]),
               "threshold": cutoff, "points": int(row["points_" + name])}
              for name, feature, cutoff, _ in RULES]
    for name, condition in [("volume_acceleration", f"vol_trend {row['vol_trend']:.3f} > 1.2 AND return {row['return']:.3f} > 0.10"),
                            ("joint_anomaly", f"price_z {row['price_z']:.3f} > 2.5 AND vol_ratio {row['vol_ratio']:.3f} > 2")]:
        result.append({"rule": name, "condition": condition, "points": int(row["points_" + name])})
    return result


def assign_tiers(intervals):
    tiers = {"tier1": [], "tier2": [], "tier3": []}
    for row in intervals.itertuples():
        n, cv = row.num_episodes, row.coefficient_variation
        tier = "tier1" if n >= 6 or (n >= 5 and cv < .4) else "tier2" if n >= 4 else "tier3"
        tiers[tier].append(str(row.ticker).upper())
    return tiers


def resolve_universe(tiers, watchlist, session, mode="union_selected"):
    if mode not in {"override", "union_tier1", "union_selected"}:
        raise ValueError("Unknown watchlist mode")
    watch = set(watchlist)
    selected = set(tiers.get("tier1", []))
    if mode == "union_selected" and pd.Timestamp(session).weekday() in (0, 2, 4):
        selected.update(tiers.get("tier2", []))
    selected = watch if mode == "override" else selected | watch
    mapping = {t: name for name, members in tiers.items() for t in members}
    return [{"ticker": t, "tier": mapping.get(t, "watchlist"), "watchlist": t in watch}
            for t in sorted(selected)]


def outcome_from_bars(bars, alert_date, sessions, as_of):
    """Evaluate exactly 10 exchange sessions, with entry and exits on one data basis.

    sessions contains the alert session and at least its next ten exchange sessions.
    Missing or invalid sessions are not compressed or filled. Final requires all 11.
    """
    day, as_of = pd.Timestamp(alert_date).normalize(), pd.Timestamp(as_of).normalize()
    expected = pd.DatetimeIndex(sessions)
    expected = expected[expected >= day][:11]
    if len(expected) != 11 or expected[0] != day:
        raise ValueError("Need exact alert session plus ten exchange sessions")
    result = {"outcome_version": OUTCOME_VERSION, "outcome": "pending", "state": "provisional",
              "horizon_sessions": 10, "due_session": str(expected[-1].date()),
              "return_1d": None, "return_5d": None, "return_10d": None,
              "worst_return_10d": None, "days_to_bottom": None}
    window = bars.reindex(expected[expected <= as_of])
    if window.empty or day not in window.index or not valid_bars(window).iloc[0]:
        return result | {"data_status": "missing_entry"}
    valid = valid_bars(window)
    if not valid.all():
        return result | {"data_status": "missing_or_invalid_session"}
    entry = float(window.iloc[0].Close)
    returns = window.Close / entry - 1
    result["evaluation_entry_price"] = entry
    for n in (1, 5, 10):
        if len(window) > n:
            result[f"return_{n}d"] = float(returns.iloc[n])
    result["worst_return_10d"] = float(returns.min())
    result["days_to_bottom"] = int(returns.index.get_loc(returns.idxmin()))
    result["data_status"] = "complete" if len(window) == 11 else "awaiting_sessions"
    if len(window) == 11:
        r1, r5, r10 = (result[f"return_{n}d"] for n in (1, 5, 10))
        sharp = r1 < -.10 or r5 < -.15 or r10 < -.20 or returns.min() < -.25 or (r5 > .05 and r10 < -.05)
        result.update(state="final", outcome="sharp_reversal" if sharp else "sustained_gain" if r5 > .05 and r10 > .05 else "mixed")
    return result


def metrics(alerts, legacy=False):
    outcomes = alerts.get("outcome", pd.Series(dtype=str))
    if legacy:
        mature = outcomes.isin(["confirmed_pump", "likely_pump", "false_positive", "uncertain"])
        positive = outcomes.isin(["confirmed_pump", "likely_pump"])
    else:
        mature = alerts.get("state", pd.Series(index=alerts.index, dtype=str)).eq("final")
        positive = outcomes.eq("sharp_reversal")
    n, k = int(mature.sum()), int((positive & mature).sum())
    rate, low, high = None, None, None
    if n:
        p, z = k / n, 1.96
        denom = 1 + z*z/n
        centre = p + z*z/(2*n)
        margin = z * sqrt(p*(1-p)/n + z*z/(4*n*n))
        rate, low, high = 100*p, 100*(centre-margin)/denom, 100*(centre+margin)/denom
    return {"total": len(alerts), "final": n, "pending": len(alerts)-n, "reversals": k,
            "rate": rate, "ci_low": low, "ci_high": high,
            "completion": 100*n/len(alerts) if len(alerts) else 0}


def score_bins(scores):
    return pd.cut(scores, [-np.inf, 55, 60, 70, np.inf], labels=["<=55", "(55,60]", "(60,70]", ">70"])
