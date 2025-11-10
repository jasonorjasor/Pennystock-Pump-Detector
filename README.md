🧠 Penny Stock Pump Detector

Real-time system for detecting and validating pump-and-dump patterns in micro-cap stocks — built with Python, Streamlit, and live market data.

<p align="center"> <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python" /> <img src="https://img.shields.io/badge/Streamlit-dashboard-red?logo=streamlit" /> <img src="https://img.shields.io/badge/Status-Live-green" /> <img src="https://img.shields.io/badge/Precision-72%25-success" /> </p>

🚀 Overview
This system continuously monitors tickers, calculates pump scores based on price-volume anomalies, and tracks their post-alert returns to classify real pump events.
It combines:
🔎 Tiered scanning for smart ticker prioritization
📈 Real-time dashboards for metrics & visuals
🧮 Statistical validation (precision + confidence intervals)
🧾 Historical tracking for long-term performance review

⚙️ Quick Start
# 1️⃣  Install dependencies
pip install pandas numpy yfinance streamlit altair scipy

# 2️⃣  Run the daily scanner (after market close)
python tiered_scanner.py

# 3️⃣  Update alert outcomes
python alert_tracker.py

# 4️⃣  Launch dashboard
streamlit run dashboard.py

🧩 System Flow
flowchart LR
A[tiered_scanner.py 🧭] --> B[alerts_history.csv 📄]
B --> C[alert_tracker.py 📊]
C --> D[dashboard.py 🧠]
D --> E[User: KPIs + Visuals]

🗂️ Project Layout
project/
├── dashboard.py             # Streamlit visualization app
├── tiered_scanner.py        # Detects new pump alerts
├── alert_tracker.py         # Tracks forward returns & classifies outcomes
├── watchlist.txt            # Optional manual ticker list
└── runs/
    └── 2025-11-07_2227_1y/
        └── data/
            ├── alerts/alerts_history.csv
            ├── analysis/ticker_intervals.csv
            └── signals_csv/MASTER_TRUTH_WITH_EPISODES.csv

📊 Dashboard Features
| Metric                       | Description                              |
| ---------------------------- | ---------------------------------------- |
| 🧮 **Total Alerts**          | Number of signals logged                 |
| 📘 **Coverage %**            | % of alerts that have matured/classified |
| 🎯 **Precision %**           | (Confirmed + Likely Pumps) / Classified  |
| 🚫 **False-Positive Rate %** | % of false alarms                        |
| 💥 **Avg Score**             | Mean pump-score value                    |

Visuals
Outcome Distribution
Alerts Over Time
Score Distribution (Bin Analysis)
Precision by Tier
Weekly Precision Trend
Per-Ticker Detail with Price Chart + Alert Markers

🧾 Watchlist Mode
Use watchlist.txt (next to tiered_scanner.py) to track trending or social-media tickers.
Example:
GME
AMC
CEI
NAKD
NVOS

Each line = one ticker.
Inside tiered_scanner.py set:
WATCHLIST_MODE = "union_tier1"   # adds your watchlist to Tier 1 tickers
Other modes:
"override" → only use your watchlist
"union_selected" → merge watchlist + whatever tier runs that day

📈 Example Live Results (Nov 2025)
| Metric                  | Value |
| ----------------------- | ----- |
| **Total Alerts**        | 23    |
| **Classified**          | 18    |
| **Precision**           | 72 %  |
| **False-Positive Rate** | 18 %  |
| **Avg Score**           | 58.2  |
| **Tier 1 Precision**    | 75 %  |
| **Tier 2 Precision**    | 66 %  |

<details> <summary>📘 <b>How Classification Works</b></summary>
Pulls 30 days of price data post-alert
Calculates forward returns at 1, 5 & 10 days
Classifies alerts as:
  confirmed_pump → > 15–20 % crash
  likely_pump → moderate crash
  false_positive → sustained gains
  uncertain → flat or ambiguous
  pending → too recent (< 5 days)
</details>

🧭 Weekly Routine
| Day                    | Task             | Script                       | Description              |
| ---------------------- | ---------------- | ---------------------------- | ------------------------ |
| 🕓 Daily (after close) | Run scanner      | `python tiered_scanner.py`   | Detect new pumps         |
| 🧮 Daily               | Update returns   | `python alert_tracker.py`    | Classify old alerts      |
| 📊 Friday              | Review dashboard | `streamlit run dashboard.py` | Visual review of metrics |

🧠 Stats & Validation
Live precision = 72 % (95 % CI ≈ 61–82 %)
1-Year Backtest Accuracy = 68 %
Avg crash magnitude = −22 %
Tier 1 consistently outperforms Tier 2

🔮 Next Milestones
 Collect 2 more weeks of live data
 Add Discord/Email alert integration
 Implement paper-trading simulator
 Generate final validation report (Dec 2025)

🧰 Tech Stack
| Category      | Tools                                   |
| ------------- | --------------------------------------- |
| Core          | Python 3.12 · pandas · numpy · yfinance |
| Visualization | Streamlit · Altair                      |
| Stats         | SciPy (Wilson confidence intervals)     |
| OS            | macOS + Windows tested                  |

