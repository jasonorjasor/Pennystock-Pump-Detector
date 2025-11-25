# 📊 Pump Detector Live Performance Report  
**Period:** 2025-11-07 → 2025-11-21  

---

## 🎯 Executive Summary

- **Total alerts generated:** 12  
- **Unique tickers monitored:** 10  
- **Classified alerts so far:** 4  
- **Coverage:** 33.3% of alerts are old enough to classify  
- **Live precision:** **75.0%** (3 / 4 classified alerts are confirmed/likely pumps)  
- **False positive rate:** **0.0%** (no false positives yet)  
- **Average PumpScore (all alerts):** 72.1  
- **Average PumpScore (classified alerts):** 60.0  

Overall, the detector is off to a **strong start**: most classified alerts are real pumps, and there are **no confirmed false positives** yet. The main limitation right now is **sample size** (only 4 classified alerts).

---

## 📁 Dataset Overview

**Alerts History Summary**

| Metric               | Value          |
|----------------------|----------------|
| Total alerts         | 12             |
| Unique tickers       | 10             |
| Period               | 2025-11-07 → 2025-11-21 |
| Classified alerts    | 4              |
| Pending alerts       | 8              |
| Coverage             | 33.3%          |
| Avg PumpScore (all)  | 72.1           |
| Avg PumpScore (classified) | 60.0     |

> Coverage will naturally increase as older alerts pass the 5–10 day window needed for classification.

---

## 🧪 Outcome Distribution

**All alerts (including pending):**

| Outcome         | Count | Percent |
|-----------------|-------|---------|
| pending         | 8     | 66.7%   |
| confirmed_pump  | 2     | 16.7%   |
| likely_pump     | 1     | 8.3%    |
| uncertain       | 1     | 8.3%    |
| false_positive  | 0     | 0.0%    |

**Among classified alerts only (4 alerts):**

- **2** = confirmed_pump  
- **1** = likely_pump  
- **1** = uncertain  
- **0** = false_positive  

From this:

- **Precision = 75.0%**  
  - (confirmed_pump + likely_pump) / classified = (2 + 1) / 4  
- **False positive rate = 0.0%**  
  - false_positive / classified = 0 / 4  

> Interpretation: every classified alert so far has either crashed (confirmed/likely pump) or moved only mildly (uncertain). No “clean winners” that would clearly count as false positives yet.

---

## 🎚 Score-Bin Analysis (Classified Alerts)

Score bins based on `pump_score` for the 4 classified alerts:

| Score Range | Count | Pumps | False Positives | Precision % | FP Rate % |
|-------------|-------|-------|-----------------|-------------|-----------|
| ≤ 55        | 2     | 1     | 0               | 50.0%       | 0.0%      |
| 60–70       | 2     | 2     | 0               | 100.0%      | 0.0%      |

Notes:

- There are **no classified alerts yet** in the **55–60** or **70+** bins.  
- Scores **60–70** are behaving very cleanly so far (100% pumps, no FPs).  
- Scores **≤55** are more mixed (only 50% pumps), but still **no** false positives yet.

> Early signal: if future data shows many weak alerts in the ≤55 bin turning into false positives, you could raise the global threshold from 50 → 55 to trade off recall for higher precision.

---

## 🧱 Tier Performance

Current classified alerts all come from **Tier 1**:

| Tier   | Classified Alerts | Precision % |
|--------|-------------------|-------------|
| tier1  | 4                 | 75.0%       |

- No Tier 2 / Tier 3 alerts are old enough to be classified yet.  
- Tier 1 performance at **75% precision** suggests the **tiering logic is doing its job**: the most “pump-prone” tickers are indeed producing higher-quality alerts.

---

## 🏆 Ticker-Level Performance

Top tickers by alert count (all alerts, classified + pending):

| Ticker | Alerts | Avg PumpScore | Precision % (classified only) |
|--------|--------|---------------|-------------------------------|
| AZI    | 2      | 80.0          | 100.0%                        |
| EPWK   | 2      | 85.0          | –                             |
| CAN    | 1      | 65.0          | –                             |
| CHGG   | 1      | 55.0          | 0.0%                          |
| CYN    | 1      | 55.0          | –                             |
| FEMY   | 1      | 65.0          | 100.0%                        |
| NFE    | 1      | 65.0          | –                             |
| PRPL   | 1      | 55.0          | 100.0%                        |
| SGMO   | 1      | 65.0          | –                             |
| SHOT   | 1      | 110.0         | –                             |

Legend:
- “Precision %” here is computed only over *classified* alerts for that ticker.
- “–” = no alerts for that ticker have matured enough to be classified yet.

Early observations:

- **AZI**, **FEMY**, and **PRPL** each have 1 classified alert and all of them are pumps → currently **100% per-ticker precision**, but with very small sample sizes.  
- **CHGG** has 1 classified alert that did *not* behave like a pump → this is your **first hint of a potential false-positive region** (score bin ≤55).

---

## 🧠 Interpretation & Next Steps

### 1. Model Quality (So Far)
- Live precision of **75%** on early data is **very strong** for a pump-detector.  
- Zero confirmed false positives is good, but this will likely change as more alerts mature.  
- Current coverage is only **33.3%**, so metrics are still noisy and should not be overfit yet.

### 2. Threshold Tuning
- Score-bin behavior suggests **60–70** is a very strong signal range.  
- The **≤55** bin is more mixed; if this bin accumulates many FPs, raising the threshold to **55** could be a good move.  
- For now, it’s reasonable to **keep the threshold at 50** until you have at least ~20 classified alerts.

### 3. Tiering Strategy
- Tier 1 (repeat-offender / high-frequency tickers) is already delivering useful, high-precision alerts.  
- Keep the current tier rules, but once Tier 2 has a couple of weeks of data, compare Tier 1 vs Tier 2 precision explicitly.

### 4. Data Collection Plan
Over the next 2–3 weeks:

- Continue running:
  - `python tiered_scanner.py`  
  - `python alert_tracker.py`  
  daily after market close.  
- Aim for at least:
  - **20–25 classified alerts**
  - **50–60 total alerts**  

This will give you a much more robust estimate of:

- True precision  
- False positive rate  
- Score-bin behavior  
- Whether the Tier 1 focus is optimal  

### 5. Future Enhancements (After More Data)
Once you have a bigger live dataset:

- Integrate **news/sentiment flags** (e.g., has_news, social_hype, legit_catalyst).  
- Compare performance of:
  - alerts with real catalysts vs  
  - alerts with no obvious news  
- Prototype a **simple ML classifier** (logistic regression or tree) on top of your rule-based PumpScore + features.

---

## 📌 Summary

- The detector is functioning **as designed**: it flags real crashes more often than not, and early precision is promising.  
- There is **no sign of the model being wildly over-trigger-happy** yet (no confirmed false positives).  
- The main bottleneck right now is **time and sample size**—you simply need more alerts to let the stats stabilize.

This report represents the **first live validation snapshot** of your system.  
Future weekly reports can be appended alongside this to show **model evolution over time**.
