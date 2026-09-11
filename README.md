# Microcap Observatory

A daily research workspace for unusual market activity, inspectable scores, and fixed-session price outcomes. See [the v2 release guide](docs/V2_RELEASE.md) for implemented features and limitations.

The [social evidence foundation](docs/SOCIAL_EVIDENCE.md) adds a versioned research universe, local JSON imports, coverage-aware attention scores, and a Social evidence dashboard tab. Run `python observatory.py social-demo` for an entirely fictional example. Live social collection and predictive accuracy are not implemented or established.

## Start here

The [research workflow](docs/RESEARCH_WORKFLOW.md) adds dashboard import previews, readiness checks, and an attention review queue. Run `python observatory.py research-readiness` to report missing prerequisites without changing data.

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

Your personal watchlist and generated runs are local files excluded from Git. On a fresh clone, initialize the reviewed starting cohort:

```powershell
Copy-Item source/MAIN/watchlist.example.txt source/MAIN/watchlist.txt
# Edit watchlist.txt before the first run.
.\.venv\Scripts\python.exe observatory.py daily
```

```powershell
.\.venv\Scripts\python.exe observatory.py daily
.\.venv\Scripts\python.exe observatory.py report
```

`daily` uses the approved candidate registry, freezes the session's exact universe, scans it, updates fixed-session outcomes, refreshes readiness, and writes a briefing. It returns status 1 when market coverage is partial. The scanner defaults to the latest completed NYSE session plus a 30-minute completion buffer. Exchange holidays and early closes are respected.

Recommended schedule:

| When | Command | Purpose |
|---|---|---|
| Every trading day, 30–60 minutes after the close | `observatory.py daily` | Scan approved tickers and update outcomes |
| Once or twice per week after `daily` | `observatory.py discover` | Find a new review batch |
| After discovery | Streamlit dashboard | Review candidates and record decisions |
| Weekly | `observatory.py candidates revalidate` | Flag listing, identity, data, and corporate-action issues |

Run the workflow consistently for at least 12 weeks before drawing conclusions about alert quality. A session with no alerts is a valid result.

Discover and review new candidates separately:

```powershell
.\.venv\Scripts\python.exe observatory.py discover
.\.venv\Scripts\python.exe observatory.py candidates list --state needs_review
.\.venv\Scripts\python.exe observatory.py candidates approve TICKER --reason "Identity and chart reviewed"
.\.venv\Scripts\python.exe observatory.py candidates reject TICKER --reason "Reason for rejection"
.\.venv\Scripts\python.exe observatory.py candidates hold TICKER --reason "Corporate action requires review"
.\.venv\Scripts\python.exe observatory.py candidates revalidate
```

Discovery reads official Nasdaq Trader symbol directories, applies security-type exclusions, computes `discovery-v1` features, and nominates no more than ten symbols. Human approval is required before a symbol enters routine scans. Approval means “include this security in future research scans”; it is not an investment recommendation or manipulation label. A session's universe remains frozen, so approvals made afterward begin with the next uncaptured completed session.

Repeated discovery for the same session returns its saved result instead of redownloading the entire market. Use `--force` only when an intentional same-session retry is necessary. Provider failures remain incomplete coverage and are not scored as normal activity. See [candidate discovery](docs/CANDIDATE_DISCOVERY.md).

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
- Review-first candidate discovery, durable state transitions, approved-universe snapshots, and quiet comparisons.
- Coverage-aware imported social evidence and separate combined-evidence classifications.
- Separate legacy display and optional reconstruction workflow. The old 49.6% metric is not the v2 success rate.

For commands, file formats, definitions, and limitations, read [the v2 release guide](docs/V2_RELEASE.md).

See [the documentation index](docs/README.md) for the release guide and audit tooling.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The current suite contains 72 fixed-data tests, including Streamlit interaction, discovery ranking, review gates, universe snapshots, social coverage, and repeatable daily runs. Local validation used Python 3.14.3. CI is configured for Python 3.12 and 3.14. `requirements-tested.txt` pins the tested direct dependencies; it is not a full transitive lockfile.

## Legacy code

The scripts under `source/MAIN/` and old run artifacts are retained for historical review. They are not the current workflow. Use `observatory.py` commands documented above.

## License

MIT License. See [LICENSE](LICENSE).
