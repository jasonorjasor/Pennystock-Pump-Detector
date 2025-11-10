#🎯 Penny Stock Pump-and-Dump Detection System

A real-time ML-based surveillance system for detecting and validating pump-and-dump manipulation in penny stocks.

This system continuously scans tickers for volume/price anomalies, assigns a PumpScore, validates predictions through forward returns, and visualizes performance metrics via a Streamlit dashboard.

###📊 Example Outputs
✅ Live Dashboard Overview

Real-time KPIs: Total alerts, classification coverage, precision (with 95% CI), and false positive rate.


✅ Price Chart with Alert Markers

Displays historical price with annotated alert markers for visual inspection.


✅ Score Distribution Analysis

Shows false positive and precision rates by score bin to optimize detection thresholds.


✅ Weekly Precision Tracking

Monitors live performance and precision trends over time.


✅ Ticker Interval Analysis

Identifies repeat-offender tickers and average time between pump cycles.


✅ Temporal Heatmap

Visualizes which days of the week pump events cluster on.


##✅ Key Features
###🔍 Real-Time Detection Engine

Scans tickers for price/volume anomalies using Yahoo Finance data

Calculates PumpScore (0-100+) from engineered statistical features

Logs new alerts to alerts_history.csv and daily snapshot files

Supports custom watchlists via watchlist.txt

###🧮 Forward Validation System

Each alert is tracked post-detection with:

Forward returns at 1, 5, and 10-day horizons

Maximum drawdown and days to bottom

Outcome classification using return thresholds

Classifications:

Outcome	Criteria
confirmed_pump	5d return < –15% or max drawdown < –25%
likely_pump	5d return < –10%
false_positive	5d return > +5%
uncertain	5d return between –10% and +5%
pending	<5 days old
###🧠 Tiered Monitoring System

Organizes tickers by recurrence frequency and consistency:

Tier	Criteria	Frequency	Purpose
Tier 1	≥ 6 pump episodes or CV < 0.4	Daily	High-priority targets
Tier 2	4–5 episodes	Mon/Wed/Fri	Secondary targets
Tier 3	< 4 episodes	Monthly	Low-frequency monitoring

Efficiency: Monitors ~60 % of tickers but captures ~80 % of pump activity.

###📈 Streamlit Dashboard

Interactive visualization panel for tracking alerts and outcomes:

KPI metrics (Total Alerts, Coverage %, Precision %, FP Rate, Avg Score)

Charts: Alerts over time, Outcome Distribution, Precision by Tier

Ticker Detail with price charts and alert markers

Score Bin Analysis and Weekly Precision Trend

###📊 Statistical Validation

Calculates Wilson 95 % confidence intervals for live precision

Aggregates coverage and false positive rate by tier

Tracks weekly precision stability

Enables data-driven threshold tuning

##🚀 Daily Workflow
# 1️⃣ Detect new pumps
python tiered_scanner.py

# 2️⃣ Update forward outcomes
python alert_tracker.py

# 3️⃣ Launch dashboard
streamlit run dashboard.py


####🕓 Run daily after market close (~4:30 PM ET)

###📁 Project Structure
project/
├── tiered_scanner.py          # Real-time detection engine
├── alert_tracker.py           # Forward validation & outcome classification
├── dashboard.py               # Streamlit dashboard
├── watchlist.txt              # Optional custom tickers
└── runs/
    └── 2025-11-07_2227_1y/
        ├── data/
        │   ├── alerts/alerts_history.csv
        │   ├── analysis/ticker_intervals.csv
        │   └── signals_csv/MASTER_TRUTH_WITH_EPISODES.csv

###📈 Example Results

1-Year Historical Backtest

345 total alerts
236 confirmed pumps
68.4 % detection precision
219 unique pump episodes
76 multi-day campaigns


Live Validation (Ongoing)

Week 1: 3 alerts (pending)
Target: 20 + classified by Week 3
Goal: 60–80 % forward precision

###🧩 Tech Stack

Python 3.12 +

pandas / numpy – data analysis

yfinance – market data ingestion

altair / matplotlib – visualization

streamlit – dashboard interface

scipy – Wilson confidence intervals

##🧠 Key Insights
✅ Early-Warning Potential

Multi-day campaigns show steadily rising PumpScores before collapse.

✅ Repeat Offenders

Tickers such as FEMY, SHOT, PRPL appear frequently across pump cycles.

✅ Opportunistic Timing

Pumps are not scheduled — chi-square test (p = 0.62) shows no weekday bias.

##📜 License

MIT License – see LICENSE for details.

##🤝 Contributing

Pull requests welcome.
Open an issue for features or bug reports.

⚠️ Disclaimer

Educational use only.
This system is not investment advice.
Pump-and-dump schemes are illegal and can cause financial loss.

<p align="center"> Built with ❤️ by [Jason Wu] | Updated November 2025 </p>
