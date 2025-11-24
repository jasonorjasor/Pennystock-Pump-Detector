import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import os
import glob
from math import sqrt  # NEW: for Wilson CI math

# ============================================================================
# CONFIGURATION
# ============================================================================

def find_latest_run():
    candidates = [
        d for d in glob.glob("runs/*/")
        if os.path.isdir(d) and os.path.basename(os.path.normpath(d)) != "LATEST"
    ]
    if not candidates:
        raise FileNotFoundError("No run directories found")
    return max(candidates, key=os.path.getmtime)

RUN_DIR = find_latest_run()
ALERTS_DIR = os.path.join(RUN_DIR, "data", "alerts")
ALERTS_HISTORY_FILE = os.path.join(ALERTS_DIR, "alerts_history.csv")
TRACKING_DAYS = [1, 5, 10]  # Check returns at 1d, 5d, 10d after alert

print("="*80)
print("PUMP ALERT TRACKER - Validation System")
print("="*80)
print(f"Using data from: {RUN_DIR}")

# ============================================================================
# LOAD ALERT HISTORY
# ============================================================================

if not os.path.exists(ALERTS_HISTORY_FILE):
    print(f"\nNo alerts history found at {ALERTS_HISTORY_FILE}")
    print("Run tiered_scanner.py first to generate alerts.")
    exit()

alerts_df = pd.read_csv(ALERTS_HISTORY_FILE)
alerts_df['alert_date'] = pd.to_datetime(alerts_df['alert_date'])
alerts_df['alert_price'] = pd.to_numeric(alerts_df['alert_price'])

print(f"\nLoaded {len(alerts_df)} historical alerts")
print(f"Date range: {alerts_df['alert_date'].min().date()} to {alerts_df['alert_date'].max().date()}")

# ============================================================================
# FORWARD RETURNS + OUTCOME RULES
# ============================================================================

def get_forward_returns(ticker, alert_date, alert_price, days_list):
    """Calculate returns at multiple time horizons after alert."""
    try:
        # Download data from alert date + 30 days to cover all horizons
        start = alert_date
        end = alert_date + timedelta(days=30)
        df = yf.download(ticker, start=start, end=end, progress=False)

        # Flatten multiindex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        if df.empty:
            return {f'return_{d}d': None for d in days_list} | {
                'max_drawdown': None, 'days_to_bottom': None
            }

        # Restrict to days on/after alert_date
        future_prices = df[df.index >= alert_date]
        returns = {}

        for target_days in days_list:
            # Pick the Nth bar after alert_date if exists; else None
            if len(future_prices) > target_days:
                actual_price = future_prices.iloc[min(target_days, len(future_prices) - 1)]['Close']
                ret = (actual_price - alert_price) / alert_price
                returns[f'return_{target_days}d'] = ret
            else:
                returns[f'return_{target_days}d'] = None

        # Max drawdown relative to alert price (even if later recovered)
        if len(future_prices) > 0:
            future_returns = (future_prices['Close'] - alert_price) / alert_price
            returns['max_drawdown'] = future_returns.min()
            returns['days_to_bottom'] = future_returns.idxmin()
        else:
            returns['max_drawdown'] = None
            returns['days_to_bottom'] = None

        return returns

    except Exception as e:
        print(f"    Error fetching {ticker}: {e}")
        return {f'return_{d}d': None for d in days_list} | {
            'max_drawdown': None, 'days_to_bottom': None
        }

def classify_outcome(row):
    """Classify alert outcome based on forward returns."""
    ret_1d = row.get('return_1d')
    ret_5d = row.get('return_5d')
    ret_10d = row.get('return_10d')
    max_dd = row.get('max_drawdown')

    # Need at least 5-day return to classify
    if pd.isna(ret_5d):
        return 'pending'

    # Confirmed pump: crashed within 5–10 days
    if ret_5d < -0.15 or (ret_10d is not None and ret_10d < -0.20):
        return 'confirmed_pump'

    # Quick reversal: down 10%+ in 1 day
    if ret_1d is not None and ret_1d < -0.10:
        return 'confirmed_pump'

    # Deep drawdown even if recovered
    if max_dd is not None and max_dd < -0.25:
        return 'confirmed_pump'

    # False positive: sustained gains
    if ret_5d > 0.05:
        return 'false_positive'

    # Uncertain: small movements
    if ret_5d > -0.10:
        return 'uncertain'

    return 'likely_pump'

# ============================================================================
# UPDATE ALERTS WITH OUTCOMES
# ============================================================================

print("\nCalculating outcomes for alerts...")
print("This may take a minute depending on number of alerts...")

updated_rows = []
for idx, row in alerts_df.iterrows():
    ticker = row['ticker']
    alert_date = row['alert_date']
    alert_price = row['alert_price']

    # Skip if already has outcome (unless pending) and recent
    if 'outcome' in row and row['outcome'] not in ['pending', None, '']:
        days_since = (datetime.now() - alert_date).days
        if days_since < 10:  # keep recent labels; revisit older ones
            updated_rows.append(row)
            continue

    days_since = (datetime.now() - alert_date).days
    print(f"  {ticker:6s} ({alert_date.date()}) - {days_since} days ago...", end=" ")

    # Get forward returns
    returns = get_forward_returns(ticker, alert_date, alert_price, TRACKING_DAYS)

    # Update row with new data
    for key, value in returns.items():
        row[key] = value

    # Classify outcome
    row['outcome'] = classify_outcome(row)
    row['days_since_alert'] = days_since
    row['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"{row['outcome']}")
    updated_rows.append(row)

# ============================================================================
# SAVE UPDATED DATA
# ============================================================================

updated_df = pd.DataFrame(updated_rows)
updated_df.to_csv(ALERTS_HISTORY_FILE, index=False)
print(f"\nUpdated alerts saved to {ALERTS_HISTORY_FILE}")

# ============================================================================
# REPORT HELPERS: Wilson CI
# ============================================================================

def wilson_ci(successes: int, trials: int, z: float = 1.96):
    """
    Wilson score interval for a binomial proportion.
    Returns (low_pct, high_pct) in percent, or (None, None) if trials == 0.
    """
    if trials == 0:
        return (None, None)
    p = successes / trials
    denom = 1.0 + (z*z) / trials
    centre = p + (z*z) / (2.0 * trials)
    margin = z * sqrt((p*(1.0 - p) + (z*z)/(4.0*trials)) / trials)
    low = (centre - margin) / denom
    high = (centre + margin) / denom
    return low * 100.0, high * 100.0

# ============================================================================
# GENERATE PERFORMANCE REPORT
# ============================================================================

print("\n" + "="*80)
print("PERFORMANCE REPORT")
print("="*80)

# Filter to alerts with outcomes (at least 5 days old)
classified = updated_df[updated_df['outcome'].isin(['confirmed_pump', 'false_positive', 'likely_pump', 'uncertain'])]
pending = updated_df[updated_df['outcome'] == 'pending']

print(f"\nTotal Alerts: {len(updated_df)}")
print(f"  Classified: {len(classified)}")
print(f"  Pending (< 5 days old): {len(pending)}")

if len(classified) > 0:
    print(f"\nOutcome Distribution:")
    outcome_counts = classified['outcome'].value_counts()
    for outcome, count in outcome_counts.items():
        pct = count / len(classified) * 100
        print(f"  {outcome:20s}: {count:3d} ({pct:.1f}%)")

    # Precision = (confirmed + likely) / classified
    pumps = len(classified[classified['outcome'] == 'confirmed_pump'])
    likely = len(classified[classified['outcome'] == 'likely_pump'])
    successes = pumps + likely
    trials = len(classified)
    precision = (successes / trials * 100.0) if trials > 0 else float("nan")
    ci_low, ci_high = wilson_ci(successes, trials)

    # Coverage
    coverage_pct = (trials / len(updated_df) * 100.0) if len(updated_df) > 0 else 0.0

    if ci_low is not None:
        print(f"\nPRECISION RATE: {precision:.1f}% (95% CI: {ci_low:.1f}-{ci_high:.1f}%)")
    else:
        print(f"\nPRECISION RATE: N/A (no classified alerts yet)")
    print("   (Confirmed + Likely Pumps) / Total Classified")
    print(f"   Coverage: {trials}/{len(updated_df)} alerts ({coverage_pct:.1f}%)")

    # Average returns by outcome
    print(f"\nAverage Returns by Outcome:")
    for outcome in ['confirmed_pump', 'likely_pump', 'uncertain', 'false_positive']:
        subset = classified[classified['outcome'] == outcome]
        if len(subset) > 0:
            avg_5d = subset['return_5d'].mean() * 100 if 'return_5d' in subset.columns else np.nan
            avg_10d = subset['return_10d'].mean() * 100 if 'return_10d' in subset.columns else np.nan
            print(f"  {outcome:20s}: 5d={avg_5d:+.1f}%  10d={avg_10d:+.1f}%")

    # Performance by tier
    print(f"\nPerformance by Tier:")
    for tier in ['tier1', 'tier2']:
        tier_alerts = classified[classified['tier'] == tier] if 'tier' in classified.columns else pd.DataFrame()
        if len(tier_alerts) > 0:
            tier_pumps = len(tier_alerts[tier_alerts['outcome'].isin(['confirmed_pump', 'likely_pump'])])
            tier_precision = tier_pumps / len(tier_alerts) * 100
            print(f"  {tier}: {tier_precision:.1f}% precision ({tier_pumps}/{len(tier_alerts)} alerts)")

    # Top alerted tickers
    print(f"\nTop Alerted Tickers:")
    ticker_counts = classified['ticker'].value_counts().head(5)
    for ticker, count in ticker_counts.items():
        ticker_alerts = classified[classified['ticker'] == ticker]
        ticker_pumps = len(ticker_alerts[ticker_alerts['outcome'].isin(['confirmed_pump', 'likely_pump'])])
        ticker_precision = ticker_pumps / len(ticker_alerts) * 100
        avg_score = ticker_alerts['pump_score'].mean() if 'pump_score' in ticker_alerts.columns else np.nan
        print(f"  {ticker:6s}: {count} alerts, {ticker_precision:.0f}% precision, avg_score={avg_score:.1f}")

# ============================================================================
# PENDING ALERTS
# ============================================================================
# WEEKLY MARKDOWN PERFORMANCE REPORT GENERATOR
# ============================================================================

def generate_markdown_report(updated_df, alerts_dir=None):
    """
    Generate a Markdown performance report and save it under:
        <run_dir>/weekly_reviews/performance_report_YYYY-MM-DD.md
    """

    import os
    import pandas as pd
    from datetime import datetime, timedelta
    from math import sqrt

    # ----------------------------
    # Resolve paths
    # ----------------------------
    # If alerts_dir not given, default to global ALERTS_DIR from this script
    if alerts_dir is None:
        alerts_dir = ALERTS_DIR

    # run_dir = parent of data/alerts → go up two levels
    run_dir = os.path.dirname(os.path.dirname(alerts_dir))
    reviews_dir = os.path.join(run_dir, "weekly_reviews")
    os.makedirs(reviews_dir, exist_ok=True)

    today_str = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(reviews_dir, f"performance_report_{today_str}.md")

    # ----------------------------
    # Basic slices
    # ----------------------------
    df = updated_df.copy()

    if "alert_date" in df.columns:
        df["alert_date"] = pd.to_datetime(df["alert_date"], errors="coerce")

    total = len(df)
    classified_df = df[df["outcome"].isin(
        ["confirmed_pump", "likely_pump", "false_positive", "uncertain"]
    )].copy()
    pending_df = df[df["outcome"] == "pending"].copy()

    classified = len(classified_df)
    pending = len(pending_df)
    coverage = (classified / total * 100) if total > 0 else 0.0

    pumps = len(classified_df[classified_df["outcome"].isin(["confirmed_pump", "likely_pump"])])
    false_pos = len(classified_df[classified_df["outcome"] == "false_positive"])

    precision = (pumps / classified * 100) if classified > 0 else 0.0
    fp_rate = (false_pos / classified * 100) if classified > 0 else 0.0

    avg_score_all = df["pump_score"].mean() if "pump_score" in df.columns else None
    avg_score_classified = (
        classified_df["pump_score"].mean() if classified > 0 and "pump_score" in classified_df.columns else None
    )

    if "alert_date" in df.columns and not df["alert_date"].isna().all():
        date_min = df["alert_date"].min().date()
        date_max = df["alert_date"].max().date()
    else:
        date_min = "N/A"
        date_max = "N/A"

    # ----------------------------
    # Wilson CI for precision
    # ----------------------------
    def wilson_ci(successes, trials, z=1.96):
        if trials == 0:
            return (None, None)
        p = successes / trials
        denom = 1.0 + (z * z) / trials
        centre = p + (z * z) / (2.0 * trials)
        margin = z * sqrt((p * (1.0 - p) + (z * z) / (4.0 * trials)) / trials)
        low = (centre - margin) / denom
        high = (centre + margin) / denom
        return low * 100.0, high * 100.0

    if classified > 0:
        ci_low, ci_high = wilson_ci(pumps, classified)
    else:
        ci_low, ci_high = (None, None)

    # ----------------------------
    # Build Markdown header
    # ----------------------------
    ci_str = (
        f"{ci_low:.1f}–{ci_high:.1f}%"
        if (ci_low is not None and ci_high is not None)
        else "N/A"
    )

    md = f"""# 📊 Pump Detector Live Performance Report
**Period:** {date_min} → {date_max}  
Generated on **{today_str}**

---

## 🎯 Executive Summary

- **Total alerts generated:** {total}
- **Classified alerts:** {classified}
- **Coverage:** {coverage:.1f}%
- **Live precision:** {precision:.1f}% (95% CI: {ci_str})
- **False positive rate:** {fp_rate:.1f}%
- **Average PumpScore (all alerts):** {avg_score_all:.1f if avg_score_all is not None else "N/A"}
- **Average PumpScore (classified alerts):** {avg_score_classified:.1f if avg_score_classified is not None else "N/A"}

---

## Outcome Distribution

"""

    # Outcome distribution table
    outcomes = df["outcome"].value_counts(dropna=False)
    md += "| Outcome | Count |\n|---------|-------|\n"
    for outcome, count in outcomes.items():
        md += f"| {str(outcome)} | {int(count)} |\n"

    # ----------------------------
    # Score-bin analysis (classified only)
    # ----------------------------
    md += """

---

## Score-Bin Analysis (Classified Only)

"""

    if classified > 0 and "pump_score" in classified_df.columns:
        bins = [0, 55, 60, 70, 9999]
        labels = ["≤55", "55–60", "60–70", "70+"]

        classified_df["score_bin"] = pd.cut(
            classified_df["pump_score"],
            bins=bins,
            labels=labels,
            include_lowest=True
        )

        md += "| Score Range | Count | Pumps | False Positives | Precision % | FP Rate % |\n"
        md += "|-------------|-------|--------|-----------------|-------------|-----------|\n"

        # for threshold analysis later
        bottom_bin = classified_df[classified_df["score_bin"] == labels[0]]

        for label in labels:
            sub = classified_df[classified_df["score_bin"] == label]
            if len(sub) == 0:
                md += f"| {label} | 0 | 0 | 0 | 0.0 | 0.0 |\n"
                continue

            cnt = len(sub)
            pumps_bin = len(sub[sub["outcome"].isin(["confirmed_pump", "likely_pump"])])
            fps_bin = len(sub[sub["outcome"] == "false_positive"])
            prec_bin = pumps_bin / cnt * 100
            fp_rate_bin = fps_bin / cnt * 100
            md += f"| {label} | {cnt} | {pumps_bin} | {fps_bin} | {prec_bin:.1f} | {fp_rate_bin:.1f} |\n"
    else:
        bottom_bin = pd.DataFrame()
        md += "_Not enough classified alerts or missing pump_score column._\n"

    # ----------------------------
    # Tier performance (classified only)
    # ----------------------------
    md += """

---

## Tier Performance (Classified Only)

"""

    if classified > 0 and "tier" in classified_df.columns:
        md += "| Tier | Alerts | Pumps | Precision % |\n"
        md += "|------|--------|-------|-------------|\n"

        tier_stats = []
        for tier_name in sorted(classified_df["tier"].dropna().unique()):
            tdf = classified_df[classified_df["tier"] == tier_name]
            if len(tdf) == 0:
                continue
            t_pumps = len(tdf[tdf["outcome"].isin(["confirmed_pump", "likely_pump"])])
            t_prec = t_pumps / len(tdf) * 100
            tier_stats.append((tier_name, len(tdf), t_pumps, t_prec))
            md += f"| {tier_name} | {len(tdf)} | {t_pumps} | {t_prec:.1f} |\n"

        if len(tier_stats) >= 2:
            # crude comparison: first two tiers in list
            diff = tier_stats[0][3] - tier_stats[1][3]
            if diff >= 5:
                md += f"\nTier **{tier_stats[0][0]}** outperforms **{tier_stats[1][0]}** by {diff:.1f} percentage points.\n"
            else:
                md += f"\nTier precision is similar across tiers (Δ ≈ {diff:.1f} pct-pts).\n"
    else:
        md += "_Tier data not available or no classified alerts yet._\n"

    # ----------------------------
    # Threshold analysis / recommendation
    # ----------------------------
    md += """

---

## 🎯 Threshold Analysis & Recommendation

"""

    if len(bottom_bin) >= 5:
        bottom_fps = len(bottom_bin[bottom_bin["outcome"] == "false_positive"])
        bottom_fp_rate = bottom_fps / len(bottom_bin) * 100

        if bottom_fp_rate > 60:
            md += (
                f"- Bottom score bin (≤55) has a **{bottom_fp_rate:.1f}%** false positive rate "
                f"over {len(bottom_bin)} alerts.\n"
                f"- **Recommendation:** Consider raising the global threshold from 50 → 55.\n"
            )
        elif bottom_fp_rate < 30 and precision > 85:
            md += (
                f"- Bottom score bin (≤55) has only **{bottom_fp_rate:.1f}%** false positives.\n"
                f"- Overall precision is **{precision:.1f}%**.\n"
                f"- **Recommendation:** You could consider lowering the threshold (e.g., 50 → 45) "
                f"to capture more pumps without introducing many false positives.\n"
            )
        else:
            md += (
                f"- Bottom score bin (≤55) has **{bottom_fp_rate:.1f}%** false positives "
                f"over {len(bottom_bin)} alerts.\n"
                f"- **Recommendation:** Keep the current threshold at 50 for now.\n"
            )
    else:
        md += (
            f"- Only **{len(bottom_bin)}** alerts in the bottom score bin (≤55).\n"
            f"- **Recommendation:** Wait for more data before changing the threshold.\n"
        )

    # ----------------------------
    # Pending alerts section
    # ----------------------------
    md += """

---

## ⏳ Pending Alerts (Too Recent to Classify)

"""

    if pending > 0:
        # Ensure days_since_alert exists, or compute on the fly
        if "days_since_alert" not in pending_df.columns:
            if "alert_date" in pending_df.columns:
                now = datetime.now()
                pending_df["days_since_alert"] = (now - pending_df["alert_date"]).dt.days
            else:
                pending_df["days_since_alert"] = None

        md += "| Ticker | Alert Date | Days Since | Classifies On |\n"
        md += "|--------|------------|------------|---------------|\n"

        for _, row in pending_df.iterrows():
            t = row.get("ticker", "")
            ad = row.get("alert_date", None)
            ds = row.get("days_since_alert", None)

            if pd.isna(ad):
                classify_on = "N/A"
                days_until = ""
                ad_str = "N/A"
            else:
                ad_str = ad.date()
                classify_date = ad + timedelta(days=5)
                classify_on = classify_date.date()
                if ds is not None:
                    days_until = 5 - ds
                else:
                    days_until = ""

            md += f"| {t} | {ad_str} | {ds if ds is not None else ''} | {classify_on} ({days_until}d) |\n"
    else:
        md += "_No pending alerts; all current alerts are classified._\n"

    # ----------------------------
    # Ticker performance (all alerts)
    # ----------------------------
    md += """

---

## 🏆 Ticker Performance (All Alerts)

"""

    if "ticker" in df.columns:
        tickers = (
            df.groupby("ticker")
            .agg(alerts=("pump_score", "count"), avg_score=("pump_score", "mean"))
            .sort_values("alerts", ascending=False)
        )

        md += "| Ticker | Alerts | Avg Score |\n|--------|--------|-----------|\n"
        for t, row in tickers.iterrows():
            md += f"| {t} | {int(row['alerts'])} | {row['avg_score']:.1f} |\n"
    else:
        md += "_No ticker column available in alerts history._\n"

    md += f"""


---

_Report automatically generated by `alert_tracker.py`._

**Saved to:**  
`{out_path}`
"""

    # ----------------------------
    # Write file
    # ----------------------------
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"\nMarkdown report saved to:\n  {out_path}\n")


if len(pending) > 0:
    print(f"\n" + "="*80)
    print(f"PENDING ALERTS (Too Recent to Classify)")
    print("="*80)

    for _, alert in pending.iterrows():
        print(f"\n{alert['ticker']:6s} - Score: {alert['pump_score']:.0f}")
        print(f"   Alert Date: {alert['alert_date'].date()}")
        print(f"   Days Since: {alert['days_since_alert']}")
        print(f"   Alert Price: ${alert['alert_price']:.2f}")
        if 'return_1d' in alert and not pd.isna(alert.get('return_1d')):
            print(f"   1-Day Return: {alert['return_1d']*100:+.1f}%")

print("\n" + "="*80)
print("TRACKING COMPLETE")
print("="*80)
print(f"\nRun this script daily to update outcomes as they mature.")
print(f"Alerts need 5+ days to be classified as pumps or false positives.")

# Generate weekly markdown performance report
generate_markdown_report(updated_df, RUN_DIR)


