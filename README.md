🎯 Penny Stock Pump-and-Dump Detection System

Real-time ML-based system for detecting and validating pump-and-dump manipulation in penny stocks.
Built with Python, yfinance, and Streamlit.

<p align="center"> <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python" /> <img src="https://img.shields.io/badge/Streamlit-Live-red?logo=streamlit" /> <img src="https://img.shields.io/badge/Status-Production-green" /> <img src="https://img.shields.io/badge/Precision-TBD-yellow" /> </p>

📘 Overview

This system monitors penny-stock tickers for pump-and-dump manipulation using
volume anomalies, price spikes, and volatility metrics.

It includes:

🔎 Real-time detection – daily post-market scans

📈 Forward validation – 1-, 5-, 10-day return tracking

📊 Tiered monitoring – focuses on high-risk tickers

🧮 Statistical confidence – precision ± 95 % CI

🧠 Interactive dashboard – KPIs, charts, and trends

🚀 Quick Start
# 1. Install dependencies
pip install pandas numpy yfinance streamlit altair scipy matplotlib

# 2. Detect new pumps (≈ 30 s)
python tiered_scanner.py

# 3. Update outcomes (≈ 2–3 min)
python alert_tracker.py

# 4. Launch dashboard
streamlit run dashboard.py

🕓 Run daily after market close (≈ 4 : 30 PM ET)

🗂️ Project Structure
project/
├── source/MAIN/
│   ├── tiered_scanner.py     # Live detection engine
│   ├── alert_tracker.py      # Forward-return validation
│   ├── dashboard.py          # Streamlit dashboard
│   ├── pump_analyzer.py      # Interval analysis
│   └── pump_detector.py      # Historical backtest
└── runs/
    └── 2025-11-07_2227_1y/
        └── data/
            ├── alerts/
            │   ├── alerts_history.csv
            │   └── pump_alerts_YYYYMMDD.csv
            ├── analysis/ticker_intervals.csv
            └── signals_csv/
                └── MASTER_TRUTH_WITH_EPISODES.csv

🔬 Methodology
📈 Detection Algorithm

Features (10) – volume z-scores, price z-scores, gap-ups, volatility, and synergy
→ combined into a pump score (0 – 100).

if vol_z > 2: score += 20
if vol_ratio > 3: score += 15
if return > 0.1: score += 20
if price_z > 2: score += 15
# ...
if score > 50:
    flag_as_pump()

🧱 Tiered Monitoring
Tier	Criteria	Frequency	Purpose
1	≥ 6 episodes or CV < 0.4	Daily	Core watchlist
2	4 – 5 episodes	Mon / Wed / Fri	Secondary list
3	≤ 3 episodes	Monthly	Archive

Monitors ~ 60 % of tickers → captures ~ 80 % of pumps.

🎯 Classification Logic
Outcome	Definition
confirmed_pump	5 d < –15 % or max drawdown < –25 %
likely_pump	5 d < –10 %
false_positive	5 d > +5 %
uncertain	–10 % ≤ 5 d ≤ +5 %
pending	< 5 days old
📊 Dashboard Highlights
KPI	Meaning
Total Alerts	All detected signals
Coverage %	Classified / Total
Precision %	Confirmed + Likely / Classified
FP Rate %	False positives / Classified
Avg Score	Mean pump score
Visuals

Alerts Over Time

Outcome Distribution

Score Bin Analysis

Precision by Tier

Weekly Precision Trend

Per-Ticker Price Charts with Alert Markers

🧪 Validation Results
📜 Historical Backtest (1 Year)

345 signals / 32 tickers

68.4 % detection accuracy

219 episodes (35 % multi-day)

Top tickers → FEMY, ORIS, SHOT

🔴 Live Validation (Nov 2025)

Week 1 active run

3 pending alerts (FEMY, AZI, PRPL)

Target → 20 classified alerts by Week 3

Goal → 60 – 80 % precision on forward data

⚙️ Technical Specs

Dependencies

pandas  numpy  yfinance  streamlit
altair  scipy  matplotlib


Data Sources

Yahoo Finance API (yfinance)

Daily updates (post-close)

One-year historical context for backtesting

🧭 Roadmap
✅ Completed

Core detection algorithm

1-year backtest (68 % accuracy)

Episode + interval analysis

Tiered monitoring framework

Live alert tracking

Streamlit dashboard

🔄 In Progress

Collect 2 weeks of live alerts

Validate precision on forward data

Score-bin threshold optimization

🔮 Planned

Discord / Email notifications

Paper-trading simulator (P&L tracking)

ML classifier if rule-based plateaus

3-year extended backtest

📈 Key Insights (from Backtest)

Pump timing is random → no calendar patterns

Repeat tickers dominate → 30 % of stocks = 80 % of pumps

Multi-day campaigns common → real-time detection is essential
