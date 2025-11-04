# Pennystock-Pump-Detector

# 🚨 Penny Stock Pump-and-Dump Detector

Detects suspicious price/volume spikes in penny stocks and distinguishes:
- ✅ Real catalysts (news, filings, partnerships)
- 📈 Sector/macro hype runs
- 🚀 Retail-driven meme pumps
- ⚠️ No-news pump-and-dump candidates

This project validates anomaly-based detection using a custom `PumpScore` and a human-labeled catalyst dataset.

---

## 📊 Labeled Validation Events

| Ticker | Date | PumpScore | Catalyst | Summary |
|---|---|---:|---|---|
| BITF | 2025-09-09 | 110 | Sector | Crypto miners moved on AI infra news |
| ONMD | 2025-10-06 | 120 | Company | Palantir partnership |
| DFLI | 2025-07-22 | 140 | Company | Preferred stock elimination |
| CIGL | 2025-09-04 | 120 | Hype | Low-float spike, retail frenzy |
| PCSA | 2025-10-07 | 120 | Company | Licensing deal |
| SES | 2025-09-18 | 95 | Company | Acquisition completion |
| YYAI | — | 105 | Unknown | No clear catalyst — suspicious |

> Dataset: `data/pump_events_labeled.csv`

---



## 🔧 Pipeline

