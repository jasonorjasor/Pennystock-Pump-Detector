# Microcap Observatory

A daily research workspace for unusual market activity, inspectable scores, and fixed-session price outcomes. See [the v2 release guide](docs/V2_RELEASE.md) for implemented features and limitations.

## Start here

On Windows, from the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c requirements-tested.txt
.\.venv\Scripts\python.exe observatory.py demo
.\.venv\Scripts\python.exe -m streamlit run dashboard/dashboard.py
```

Select **Observatory / demo_v2** in the sidebar for the offline demonstration. A fresh clone generates fictional data; if local historical bars exist, it replays those instead. Both use October 24, 2025 and evaluate through November 7. The data source is labeled explicitly. The local historical demo includes one invalid ticker and exits with status 1 for partial coverage; the synthetic demo exits with status 0.

After installing dependencies, subsequent starts only need the Streamlit command. On macOS/Linux, use `.venv/bin/python` instead of `.venv\Scripts\python.exe`.

## Daily use

Your personal watchlist and generated runs are local files excluded from Git. On a fresh clone, initialize the watchlist and use override mode until you have built historical tiers:

```powershell
Copy-Item source/MAIN/watchlist.example.txt source/MAIN/watchlist.txt
# Edit watchlist.txt with the symbols you want to research.
.\.venv\Scripts\python.exe observatory.py scan --watchlist-mode override
```

```powershell
.\.venv\Scripts\python.exe observatory.py scan
.\.venv\Scripts\python.exe observatory.py track
.\.venv\Scripts\python.exe observatory.py report
```

The scanner defaults to the latest completed NYSE session plus a 30-minute completion buffer. It includes Tier 1 and the watchlist daily, and Tier 2 on Monday/Wednesday/Friday. Exchange holidays and early closes are respected. New state goes into `runs/observatory_v2/`; the old run is not modified.

Replay or choose inputs explicitly:

```powershell
python observatory.py scan --session 2026-09-08 --historical-run runs/2025-11-07_2227_1y
python observatory.py scan --watchlist-mode override --watchlist source/MAIN/watchlist.txt
python observatory.py backtest --start 2025-01-01 --end 2025-11-07 --tickers FEMY PRPL
```

Live commands download data from Yahoo through yfinance. An old historical run supplies old tiers; create a new historical run when refreshing the monitored universe. Historical replays are retrospective, not proof of out-of-sample prediction. `--prices-dir` on scan, track, or backtest reads local `TICKER.csv` or `TICKER/signals.csv` instead of downloading.

The existing `source/MAIN/` scripts remain compatibility entrypoints. Historical analysis now writes a new v2 run with `MASTER_OUTCOMES.csv`, `ACTIVITY_EPISODES.csv`, and descriptive intervals. Old pump-named CSVs, PNG reports, and automatic cycle-prediction claims are not regenerated.

## What changed

- One shared score with prior-session baselines and a strict `score > 50` threshold; maximum 130 points.
- Exactly ten exchange sessions for final outcomes; missing bars are never silently filled or compressed.
- Neutral outcomes: `sharp_reversal`, `sustained_gain`, `mixed`, or `pending`. These are price patterns, not manipulation findings.
- Immutable successful observations and finalized outcomes, atomic files, and a shared writer lock.
- Full scan-status records, archived input bars, per-rule explanations, and consistent dashboard denominators.
- A research queue, ticker event timeline, and editable notes with evidence URLs.
- Separate legacy display and optional reconstruction workflow. The old 49.6% metric is not the v2 success rate.

For commands, file formats, definitions, and limitations, read [the v2 release guide](docs/V2_RELEASE.md).

See [the documentation index](docs/README.md) for the release guide and audit tooling.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use fixed local data, including Streamlit interaction checks. Local validation used Python 3.14.3. CI is configured for Python 3.12 and 3.14; those hosted jobs have not yet run. `requirements-tested.txt` pins the tested direct dependencies; it is not a full transitive lockfile.

## Legacy reference: pre-v2 pipeline

The material below is retained from the original README for historical context. Its output schemas, score description, classifications, and performance claims describe the old implementation, not the new engine above.

A Python surveillance and validation pipeline for micro-cap equities. The project scores penny stocks for abnormal volume, price, and volatility behavior, clusters repeated signals into episodes, and tracks forward returns to evaluate whether alerts behave like pump-and-dump events.

## Summary

This project combines:

- Historical backtesting on one year of daily market data
- A rule-based PumpScore for live monitoring
- Episode clustering to identify repeat-offender tickers
- Forward validation at 1, 5, and 10 days
- A Streamlit dashboard plus automated CSV, JSON, and Markdown reporting

## Current Validation Snapshot

Latest saved run: `2026-04-20`

- Total alerts: 123
- Classified alerts: 115
- Pending alerts: 8
- Precision: 49.6% (95% CI 40.6-58.6%)
- Coverage: 93.5%
- Confirmed pumps: 57
- False positives: 50
- Uncertain: 8

Precision is measured on classified alerts only and updates as alerts mature. Older snapshots are preserved in `runs/` so performance can be reviewed over time instead of treated as a single fixed number.

## What The System Does

1. Builds a historical signal set from one year of price and volume data.
2. Groups nearby signals into multi-day episodes to model repeated pump campaigns.
3. Assigns tickers to monitoring tiers based on episode frequency and consistency.
4. Scans the active universe daily, scores each ticker, and writes alerts to disk.
5. Rechecks alerts after 1, 5, and 10 days to label outcomes and update reports.
6. Surfaces the results in a dashboard for quick review.

## Project Flow

| Stage | Script | Output |
| --- | --- | --- |
| Historical backtest | `source/MAIN/pump_detector.py` | Signal-level CSVs with forward returns and drawdown metrics |
| Episode analysis | `source/MAIN/pump_analyzer.py` | `PUMP_EPISODES.csv` and `ticker_intervals.csv` |
| Tiered live scan | `source/MAIN/tiered_scanner.py` | `pump_alerts_YYYYMMDD.csv` and `alerts_history.csv` |
| Forward validation | `source/MAIN/alert_tracker.py` | Weekly Markdown reports and daily JSON snapshots |
| Dashboard | `dashboard/dashboard.py` | Streamlit UI for KPIs, score bins, and ticker drill-downs |

## Scoring Approach

The PumpScore is intentionally interpretable. It uses rolling daily features over 20 trading days and adds points when the current bar looks abnormal relative to the ticker's own history.

| Feature | What It Measures |
| --- | --- |
| `vol_z` | Volume spike relative to the 20-day baseline |
| `vol_ratio` | Current volume versus 20-day average volume |
| `vol_trend` | 5-day volume acceleration versus 20-day average |
| `return` | Large daily price move |
| `price_z` | Return anomaly versus 20-day baseline |
| `gap_up` | Open versus previous close gap |
| `volatility` | Intraday range expansion |
| `synergy` | Multiple signals firing together |

Alerts trigger when `PumpScore >= 50`.

## Monitoring Tiers

Tickers are ranked by how often they have historically produced episodes.

- Tier 1: 6+ episodes, or 5 episodes with low variation, monitored daily
- Tier 2: 4-5 episodes, monitored Monday/Wednesday/Friday
- Tier 3: below that threshold, ignored by the live scanner

A `watchlist.txt` file can be used to override or augment the tiered universe.

## Outputs

Each run writes a reproducible audit trail into `runs/<timestamp>/`:

- `data/signals_csv/MASTER_TRUTH_WITH_EPISODES.csv`
- `data/signals_csv/PUMP_EPISODES.csv`
- `data/analysis/ticker_intervals.csv`
- `data/alerts/alerts_history.csv`
- `daily_snapshots/YYYY-MM-DD.json`
- `weekly_reviews/report_YYYY-MM-DD.md`

## Tech Stack

- Python 3.12+
- pandas
- numpy
- yfinance
- scipy
- matplotlib
- streamlit
- altair

## How To Run

Install dependencies first:

```bash
pip install -r requirements.txt
```

Then run the pipeline:

```bash
# One-time historical analysis
python source/MAIN/pump_detector.py
python source/MAIN/pump_analyzer.py

# Daily monitoring
python source/MAIN/tiered_scanner.py

# Weekly validation
python source/MAIN/alert_tracker.py

# Dashboard
streamlit run dashboard/dashboard.py
```

## Notes

- The project is designed for interpretability and forward validation, not machine learning model fitting.
- The live precision metric changes over time as more alerts mature.
- The latest saved snapshot is the best source of truth for performance claims.

## Disclaimer

This project is for educational and research purposes only. It is not financial advice, not a trading system, and not a guarantee of future market behavior. Penny stocks are high risk, and false positives are expected.

## License

MIT License. See [LICENSE](LICENSE).

## Contact

- Email: jasonorjasor@gmail.com

Built with curiosity, validated with data.
