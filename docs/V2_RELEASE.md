# Observatory v2: first usable release

This release implements shared scoring, bounded outcomes, deterministic universe selection, scan health, offline replay, and a daily research dashboard. It also includes observation notes and a descriptive event timeline. It does not implement automatic filings/social ingestion, machine learning, trading, notification delivery, or cloud hosting.

## Commands

Run from the repository root using the project virtual environment. Script entrypoints can be invoked by absolute path from another directory; explicit relative file arguments are relative to the shell except `--historical-run`, which resolves relative to the project.

| Command | Purpose |
|---|---|
| `python observatory.py demo` | Uses local archived data or generates fictional data into `runs/demo_v2`; no network |
| `python observatory.py scan` | Checks latest completed session into `runs/observatory_v2` |
| `python observatory.py track` | Refreshes provisional ten-session outcomes |
| `python observatory.py report` | Reads current metrics without downloads |
| `python observatory.py backtest` | Creates a new historical run with shared rules |
| `python observatory.py analyze --run runs/<v2-history>` | Rebuilds descriptive activity episodes for a v2 historical run |
| `python -m streamlit run dashboard/dashboard.py` | Opens the research application |

Use `--help` after any subcommand. The old scanner, tracker, detector, analyzer, and diagnostic filenames delegate to scan, track, backtest, analyze, and report respectively. Importing them does not run a pipeline.

`scan` and `daily` now default to the approved candidate registry. The first run seeds that registry from the local reviewed watchlist, and every session captures an immutable universe snapshot. `union_selected` and `union_tier1` remain available for explicit legacy-tier research; `override` uses only the supplied watchlist. Each ticker appears once. Blank lines and `#` comments are allowed in a watchlist.

Exit code 0 means completion; 1 means a partial scan/update; 2 means invalid configuration. A run with zero alerts can be completely healthy. With the original local archive, the demo exposes one invalid ticker and reports partial coverage. Without that archive, it generates fictional OHLCV and completes normally. Neither demo supports a predictive-performance claim.

## Outcome definition

The alert session is session zero. The next ten NYSE sessions define the horizon. A record is provisional until all eleven required bars, including entry, are valid and completed. The tracker reads all evaluation prices from the same snapshot, preserving the originally observed alert price separately.

A final `sharp_reversal` occurs if any of these conditions hold:

- Session 1 return below -10%.
- Session 5 return below -15%.
- Session 10 return below -20%.
- Worst closing return from the entry through session 10 below -25%.
- Session 5 return above +5% followed by session 10 return below -5%.

Otherwise, `sustained_gain` requires returns above +5% at both sessions 5 and 10. Other mature records are `mixed`. Boundaries are strict. These heuristic rules are versioned as `reversal-10s-v2`; they have not been calibrated as a predictive model.

The `worst_return_10d` field is a return relative to the alert-session close, not conventional peak-to-trough drawdown. `days_to_bottom` counts trading sessions. Missing/invalid sessions leave the outcome provisional and appear in the tracking attempt log. Prior valid values survive a failed refresh. Finalized records are never automatically recomputed; to evaluate revised data or rules, use a separate workspace/version.

## Scoring

`activity-v2` uses prior 20-session means and standard deviations for volume/return anomalies. Price and volume are not filled. The score retains the two synergy rules and totals at most 130 points. Eligibility requires valid positive OHLCV, sensible high/low relationships, sufficient history, and no daily discontinuity exceeding 500%. A score of exactly 50 does not alert.

The dashboard explanation table stores individual rule points and observed feature values. The joint rules refer to feature values in the archived observation. Changing the baseline and version means v2 scores should not be treated as equivalent to old scores.

## Output and preservation

Each v2 workspace contains:

```text
workspace.json           dataset kind and score version
observations.csv         successful observations plus unresolved failures
outcomes.csv             provisional/final outcome state
alerts.csv               derived alert/outcome export
summary.json             shared cohort metrics
briefing.md              concise generated report
latest_scan.json         latest scan status and universe
latest_tracking.json     latest outcome update status
notes.json               user research notes, when present
attempts/<id>/           manifests, input bars, and per-ticker status
```

Successful ticker/session/score-version observations are immutable. A re-run records a new attempt, but cannot replace the first valid observation. Failed observations can be replaced after a successful retry. Input CSV snapshots have SHA-256 hashes. Update attempts record outcome data issues separately from outcomes.

Offline scans require a dedicated `--workspace`; they cannot use the default live destination. A workspace's provider mode must remain consistent when scanning and tracking. Reconstructed legacy cohorts are explicitly separate and can use either reconstruction source mode.

Writes use atomic replacement and a shared exclusive lock; attempts retain progress if interrupted. This is a single-writer local design, not a transactional database spanning all files. Derived exports can be regenerated by tracking. If a process crashes leaving `.writer.lock`, verify its PID is no longer running before removing that lock. Do not run writers on different computers against the same synced folder. A proper local database and multi-file transaction design remain future work.

The original `runs/2025-11-07_2227_1y/` is read-only to the new workflows. Legacy dashboard metrics retain their original definitions and warnings. To reconstruct price outcomes without changing that archive:

```powershell
python observatory.py import-legacy runs/2025-11-07_2227_1y/data/alerts/alerts_history.csv --workspace runs/reconstructed_v2
python observatory.py track --workspace runs/reconstructed_v2
```

Import copies alert observations and marks their score version `legacy-unversioned`; it does not copy old outcome labels. It requires an empty destination. Fresh price downloads may differ from data available at the original alert time, so reconstruction is not a pristine historical replay. New scans cannot be mixed into that reconstructed cohort. This reconstruction was not run as part of the release.

## Using the dashboard

Select the dataset in the sidebar. The default live workspace may be empty before the first scan; choose `demo_v2` to explore immediately. The daily status reports coverage and source age. Queue filters affect the table/export only. Evaluation always uses the entire selected dataset, with final observations as its denominator.

The ticker notebook shows events grouped by a seven-calendar-day gap. This grouping describes activity, not coordination. Select an observation to see its score explanation, archived prices/volume, and saved notes. Evidence URLs and publication times are entered manually; the application does not fetch or verify those sources. Notes attach to the ticker and observation date so appending events does not move them.

## Verification and limits

Offline tests cover scoring parity and time direction, missing bars, adjustment-basis consistency, fixed horizons, pending/final behavior, tier membership, duplicate execution, retained outcomes on failures, empty states, holidays/early closes, safe legacy import, writer locks, and Streamlit notes/filter behavior.

The demo uses existing saved bars and was checked in the dashboard. The real legacy dashboard shows 123 alerts, 115 classified, and 49.6% legacy positive-label share. Live Yahoo download availability, provider limits, externally hosted CI, and current-symbol coverage were not verified by a live market scan.

The engine currently uses the NYSE calendar as the common U.S. equity calendar; venue-specific differences require another adapter. It does not implement point-in-time issuer identities, automated split investigation, matched baselines, event recall, calibrated probabilities, or a trading simulation. An old tier file remains old even when scanning current prices: refresh historical inputs deliberately and use explicit run selection for reproducibility.

Original audit findings and their evidence are retained. The audit script now extracts the pre-release functions from pinned Git commit `6d21d5171292d1615a33e0dbf9cdf1c21e1fc1f3` so its bug reproductions do not accidentally target the repaired wrappers. It requires that commit in the local Git history; use the new tests to verify current behavior.

## Social evidence addition

The optional [social evidence foundation](SOCIAL_EVIDENCE.md) now provides versioned research candidates, local evidence imports, coverage-aware experimental attention scores, and a Streamlit chronology. It uses separate social state and does not change the market score or outcome rules. See its guide for current commands and explicit limitations; there is no live social collector yet.
