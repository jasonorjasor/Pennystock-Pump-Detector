🚨 Penny Stock Pump Detector

A real-time system that detects, validates, and tracks pump-and-dump manipulation in small- and micro-cap stocks.

This engine continuously analyzes market data, flags statistical anomalies, assigns a PumpScore, clusters coordinated campaigns, and tracks outcomes across time — all visualized through a live Streamlit dashboard.

📊 Example Outputs
✅ Real-Time Pump Alerts

Automatic alerts showing live pump candidates with their PumpScore and classification.


✅ Pump Interval Analysis

Identifies repeat offenders and measures average time between pump cycles.


✅ Temporal Heatmap

Visualizes which weekdays and time periods pumps most frequently occur.


✅ Key Features
🔍 1. Live Detection Engine

Scans tickers for price/volume anomalies using real-time market data

Computes a dynamic PumpScore (0–100+)

Automatically logs signals exceeding threshold

Saves timestamped CSV alerts and appends to history

🧮 2. Forward Validation Tracker

Every alert is tracked for 1, 5, and 10-day returns:

return_1d, return_5d, return_10d

max_drawdown, days_to_bottom

Auto-updated daily via alert_tracker.py

🧠 3. Auto Classification

Alerts are automatically labeled based on forward returns:

confirmed_pump – sharp crash post-alert

likely_pump – moderate crash (–10% to –20%)

false_positive – continued growth or flat

uncertain – minor movement

pending – too recent (<5 days)

🗂️ 4. Tiered Monitoring System

Organizes tickers by recurrence frequency and consistency:

Tier	Criteria	Frequency	Purpose
Tier 1	≥ 6 pump episodes or low variance	Daily	High-priority list
Tier 2	4–5 pump episodes	Mon / Wed / Fri	Secondary watchlist
Tier 3	< 4 episodes	Ignored	Low signal

Efficiency: Monitors ~60% of tickers but captures ~80% of true pumps.

📈 5. Streamlit Dashboard

Interactive front-end for live metrics & visualization.

Features include:

KPI tiles: total alerts, coverage %, precision %, FP rate

Charts:

Alerts Over Time

Outcome Distribution

Precision by Tier

Weekly Precision Trend

Ticker Detail with price chart & alert markers

Score Bin Analysis for tuning thresholds

⚙️ How It Works
✅ Step 1 — Tiered Scanner
python tiered_scanner.py


Scans all tickers (or watchlist.txt) → generates daily alerts → appends to alerts_history.csv.

✅ Step 2 — Outcome Tracker
python alert_tracker.py


Pulls post-alert returns via Yahoo Finance → classifies each alert → updates outcomes.

✅ Step 3 — Dashboard
streamlit run dashboard.py


Displays KPIs, charts, and per-ticker performance.

🧠 Example Analysis Insights
✅ Early Warnings Exist

Multi-day pump campaigns often show rising PumpScores before the crash, indicating predictive potential.

✅ Repeat Offenders

Tickers such as FEMY, SHOT, and PRPL frequently reappear — chronic manipulation patterns exist.

✅ Temporal Clustering

Pumps often occur mid-week (Wed/Thu) — shown by your temporal heatmap.

🧰 Tech Stack

Python 3.12+

pandas / numpy – data analysis

yfinance – market data ingestion

matplotlib / altair – visualization

streamlit – dashboard front-end

scipy – confidence intervals

📁 Project Structure
project/
├── tiered_scanner.py         # Detects new alerts
├── alert_tracker.py          # Updates outcomes
├── dashboard.py              # Streamlit dashboard
├── watchlist.txt             # Optional custom tickers
└── runs/
    └── 2025-11-07_2227_1y/
        ├── data/
        │   ├── alerts/alerts_history.csv
        │   ├── analysis/ticker_intervals.csv
        │   └── signals_csv/MASTER_TRUTH_WITH_EPISODES.csv

📈 Example Summary (Backtest)
Total alerts detected: 345
Confirmed pumps: 236
Precision (historical): 68.4%

Total episodes: 219
Multi-day campaigns: 76
Repeat offenders: 11 tickers

✅ Pumps cluster on Wed/Thu
✅ Tier 1 captured 80% of pumps
✅ Forward validation in progress

🚀 Getting Started
git clone https://github.com/yourname/penny-pump-detector.git
cd penny-pump-detector
pip install -r requirements.txt

# Run analysis
python tiered_scanner.py
python alert_tracker.py
streamlit run dashboard.py


Run daily after market close for live validation.

📜 License

MIT License – see LICENSE for details.

🤝 Contributing

Pull requests welcome.
Open an issue for feature ideas or bug reports.

⚠️ Disclaimer

For educational use only.
This system is not investment advice and should not be used for live trading.
Pump-and-dump manipulation is illegal and high-risk.

<p align="center"> Built with ❤️ by [Jason Wu] — Updated November 2025 </p>
