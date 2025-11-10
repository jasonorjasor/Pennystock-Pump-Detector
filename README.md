# 🎯 Penny Stock Pump-and-Dump Detection System
A real-time ML-based surveillance system for detecting and validating pump-and-dump manipulation in penny stocks.

This system monitors 32 micro-cap tickers, calculates pump scores from volume/price anomalies, validates predictions with forward returns, and provides live dashboards for tracking precision and false positive rates.

---

## 📊 Example Outputs

### ✅ Live Alert Dashboard
Real-time KPIs: Total alerts, coverage, precision (with confidence intervals), and false positive rate.  
![Dashboard Screenshot](assets/dashboard_preview.png)

---

### ✅ Score Distribution Analysis
Shows precision by score range to optimize threshold tuning.  
![Score Bins](assets/score_bins.png)

---

### ✅ Episode Progression Analysis
Tracks whether pump scores escalate across multi-day campaigns (tests early-warning capability).  
![Episode Progression](runs/LATEST/data/analysis/episode_progression.png)

---

### ✅ Ticker Interval Predictions
Identifies repeat-offender tickers and average pump cycle duration.  
![Ticker Intervals](runs/LATEST/data/analysis/ticker_intervals.png)

---

### ✅ Temporal Clustering Heatmap
Visualizes which days/weeks pumps concentrate on (chi-square test: p=0.62, not significant).  
![Temporal Heatmap](runs/LATEST/data/analysis/temporal_heatmap.png)

---

## ✅ Key Features

### 🔍 **1. Tiered Monitoring System**
- **Tier 1:** Daily monitoring (6+ episodes or CV <0.4)
- **Tier 2:** 3x/week monitoring (4-5 episodes)
- **Tier 3:** Monthly monitoring (2-3 episodes)
- **Efficiency:** Monitors 62% of tickers, catches 80% of pumps

### 📈 **2. Forward Validation System**
Every alert is tracked with:
- 1, 5, 10-day forward returns
- Max drawdown in next 20 days
- Days to bottom
- Classification: `confirmed_pump`, `likely_pump`, `false_positive`, `uncertain`, `pending`

### 🧠 **3. Statistical Rigor**
- **Precision:** (Confirmed + Likely Pumps) / Classified
- **Coverage:** % of alerts old enough to classify
- **Wilson Confidence Intervals:** 95% CI for precision
- **Score-Bin Analysis:** FP rate by score range

### 🗂️ **4. Episode Detection**
Groups signals within 7-day windows into coordinated campaigns:
- `episode_key` (unique identifier)
- `signal_count` (multi-day vs single-day)
- `avg_pump_score`, `duration_days`
- `episode_pump_rate` (% confirmed)


