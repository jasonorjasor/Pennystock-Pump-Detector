<div align="center">🎯 Penny Stock Pump-and-Dump Detection System</div>
<div align="center">

A real-time surveillance engine for detecting, validating, and analyzing pump-and-dump activity in micro-cap stocks.

Built with Python, Streamlit, and Yahoo Finance data.

<br>










</div>
🚀 Key Features

🔍 Real-Time Detection Engine

Scans all tickers daily after market close

Computes:

Volume Z-score

Gap-up percentage

Intraday volatility

Return anomalies

10+ engineered features

Produces a PumpScore (0–100+)

Logs all signals to alerts_history.csv

🧮 Forward Validation System

Tracks each alert for 20 days post-signal:

return_1d, return_5d, return_10d

max_drawdown + days_to_bottom

Classifies into:

Outcome	Meaning
confirmed_pump	clear pump/crash event
likely_pump	moderate crash
false_positive	price continued rising
uncertain	ambiguous movement
pending	<5 days old
🧠 Tiered Monitoring
Tier	Criteria	Frequency	Purpose
Tier 1	≥6 episodes or CV < 0.4	Daily	High-risk repeat offenders
Tier 2	4–5 episodes	M/W/F	Medium risk
Tier 3	Low-frequency	Monthly	Baseline monitoring

✔ Catches 80% of pumps scanning 60% of tickers.

📈 Streamlit Dashboard

Features:

KPI cards

Precision %, Coverage %, FP Rate

Score Bin Analysis

Alerts Over Time

Precision by Tier

Weekly Precision Trend

Ticker-level drill-down with price charts and alert markers

CSV download buttons

📊 Statistical Validation

Wilson 95% Confidence Interval

Tier-specific performance

Score bin behavior

Weekly precision trend

Threshold optimization recommendations

🗂️ Project Structure
project/
├── tiered_scanner.py          # Real-time detection
├── alert_tracker.py           # Forward validation
├── dashboard.py               # Streamlit UI
├── watchlist.txt              # Custom tickers
└── runs/
    └── 2025-11-07_2227_1y/
        ├── data/
        │   ├── alerts/alerts_history.csv
        │   ├── analysis/ticker_intervals.csv
        │   └── signals_csv/
        │       ├── MASTER_TRUTH.csv
        │       └── MASTER_TRUTH_WITH_EPISODES.csv

⏱️ Daily Workflow
# 1. Detect pump alerts
python tiered_scanner.py

# 2. Update forward returns + classifications
python alert_tracker.py

# 3. Launch dashboard
streamlit run dashboard.py


Run daily at ~4:30 PM ET (after market close)

📈 Results
📘 1-Year Historical Backtest

345 total signals

236 confirmed pumps

68.4% backtested detection accuracy

219 pump episodes

76 multi-day schemes

📗 Live Results (Nov 7 → Nov 21, 2025)

(Using your actual uploaded data)

12 alerts generated

3 classified so far

Precision: 75%

0 false positives

Average PumpScore: 72.1

Repeat-offenders emerging:

AZI, EPWK, FEMY, PRPL

System performing exactly as intended.

🧠 Key Insights

Pump timing is opportunistic, not scheduled

Multi-day pumps show increasing PumpScores (early-warning signal)

Certain tickers are consistent manipulation targets

Score bins below 55 likely need threshold adjustment

🔮 Roadmap
✔ Completed

Real-time detector

Forward validator

Dashboard

Tier system

Historical backtest

Confidence intervals

🔄 In Progress

Live validation (20–25 alerts target)

Threshold optimization

🔮 Future

Reddit / Twitter sentiment scraper

Hype-score integration

Paper-trading backtester

ML classifier (if rule-based plateaus)

🛠️ Tech Stack

Python 3.12

pandas, numpy

yfinance

altair, matplotlib

streamlit

scipy

📜 License

MIT License

⚠️ Disclaimer

For educational use only.
Not financial advice.
Pump-and-dump activity is illegal.

<div align="center">

Built with ❤️ by Jason Wu
Updated: November 2025

</div>
