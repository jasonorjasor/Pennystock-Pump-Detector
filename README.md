🚀 Pump-and-Dump Detection System

A fully automated pipeline for detecting and validating potential pump-and-dump trading patterns in micro-cap stocks.

🧠 Overview

This system monitors a set of U.S. small-cap and OTC tickers daily, scoring them based on price-volume anomalies and identifying potential pump events.
It combines real-time monitoring, tiered scanning, performance tracking, and a Streamlit dashboard for live visualization.

📁 Project Structure
project/
├── dashboard.py                 # Streamlit dashboard for visualization
├── tiered_scanner.py            # Daily scanner that detects new pump alerts
├── alert_tracker.py             # Tracks alert performance and outcomes
├── watchlist.txt                # Optional: custom tickers to monitor
├── runs/
│   └── 2025-11-07_2227_1y/     # Example run folder with data outputs
│       ├── data/
│       │   ├── alerts/
│       │   │   └── alerts_history.csv
│       │   ├── analysis/
│       │   │   └── ticker_intervals.csv
│       │   └── signals_csv/
│       │       └── MASTER_TRUTH_WITH_EPISODES.csv
└── README.md

⚙️ System Components
1. tiered_scanner.py

Detects pump candidates using volume and price anomalies.

Assigns tickers into Tier 1 (daily) and Tier 2 (weekly) based on historical activity.

Supports a manual watchlist.txt for focused monitoring.

Modes:

WATCHLIST_MODE = "override" → only use your watchlist.

WATCHLIST_MODE = "union_tier1" → watchlist + Tier 1 tickers (recommended).

WATCHLIST_MODE = "union_selected" → watchlist + whichever tier is scheduled that day.

Output:

data/alerts/alerts_history.csv (master log)

Daily CSVs like pump_alerts_20251109.csv

2. alert_tracker.py

Calculates forward returns (1-, 5-, 10-day) for each alert.

Classifies alerts as:

confirmed_pump (crashed post-spike)

likely_pump

false_positive

uncertain

pending

Adds 95 % confidence intervals for precision using Wilson CI.

Example console output:

PRECISION RATE: 71.4% (95% CI: 61.2–82.3%)
Coverage: 18/25 alerts (72%)

3. dashboard.py

Streamlit web app for interactive exploration of alerts.

Features include:

KPI tiles → total alerts, coverage %, precision %, false-positive %, avg score

Score distribution analysis (false-positive rate by score range)

Outcome distribution & alerts over time

Performance by tier and weekly precision trends

Per-ticker detail view with price chart + alert markers

Run locally:

streamlit run dashboard.py

🕒 Daily & Weekly Routine
Step	When	Script	Purpose
1️⃣	After market close (daily)	python tiered_scanner.py	Detect new alerts
2️⃣	Immediately after scanner	python alert_tracker.py	Update outcomes for existing alerts
3️⃣	Weekly (Friday)	streamlit run dashboard.py	Visualize trends & performance
📊 Key Metrics

Precision = (confirmed + likely pumps) / classified alerts

Coverage = (classified alerts) / total alerts

False-Positive Rate = (false positives) / classified alerts

Example KPI snapshot:

Metric	Value
Total Alerts	23
Coverage	78.3 %
Precision	71.4 %
FP Rate	21.0 %
Avg Score	58.2
🧾 Watchlist Configuration

Optional file: watchlist.txt

Place it in the same directory as tiered_scanner.py.

Example:

GME
AMC
CEI
NAKD
NVOS


Each line = one ticker.
By default (WATCHLIST_MODE = "union_tier1"), these tickers are added to your Tier 1 set.

📈 Example Results (as of Nov 9 2025)
Metric	Result
Backtest Accuracy	68.4 % (1-year historical)
Live Precision	72 % (first 2 weeks)
Tier 1 Precision	75 %
Tier 2 Precision	67 %
Average Crash Magnitude	−22 %
🧩 Next Milestones

 Collect 2 more weeks of live data (15–20 alerts target)

 Validate precision on forward data

 Add auto Discord/email notifications

 Paper trading simulator for strategy testing

📅 Version Log
Date	Update
Nov 7 2025	Completed 1-year backtest
Nov 8 2025	Dashboard operational (3 charts)
Nov 9 2025	Added coverage + FP Rate KPI, score-bin analysis, confidence intervals
🧰 Tech Stack

Python 3.12+

pandas, numpy, yfinance

streamlit, altair

scipy (for confidence intervals)

Project tested on macOS and Windows

💡 Tips

If you see no new alerts, try lowering PUMP_THRESHOLD from 50 → 45.

If many false positives appear, raise it to 55–60.

Always verify your runs/ folder path is valid.

watchlist.txt must be in the same directory as tiered_scanner.py.

🏁 Author Notes

This system combines quantitative anomaly detection with real-time tracking and validation.
It’s designed to evolve: as more alerts accumulate, thresholds and tier logic can be tuned using empirical data.

Last updated: Nov 9 2025
