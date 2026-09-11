# Methodology

Microcap Observatory records unusual market and public-attention evidence for prospective research. It does not determine whether manipulation occurred and does not generate investment recommendations.

## Sessions and data quality

Market workflows use the NYSE calendar and a 30-minute completion buffer. A requested date must be a completed session. Daily OHLCV data must contain positive prices and volume, valid high/low relationships, and enough prior observations for the relevant calculation.

Missing, stale, partial, and failed downloads remain explicit coverage states. They do not become zero activity. Live market data currently comes from yfinance with adjusted prices. Offline workflows accept one consistent adjustment basis through `--prices-dir`.

## Candidate discovery

Discovery reads the current Nasdaq and other-listed symbol directories published by Nasdaq Trader. Common shares and ADR/ADS securities are eligible. ETFs, funds, warrants, rights, units, preferred shares, test issues, and securities without sufficient history are excluded.

The default price ceiling is $5 and can be changed with `--max-price`. Listing deficiencies, low prices, and corporate actions are context fields; none establishes manipulation.

`discovery-v1` calculates these values using information available through the selected session:

- Latest adjusted close
- Prior 20-session median dollar volume
- Current volume ratio and z-score against the prior 20 sessions
- 1-, 5-, and 20-session returns
- Opening gap and intraday range
- Valid-session count
- Quiet-baseline indicator
- Listing and collection status

The score awards points for unusual volume, unusual positive return, adequate dollar volume, emergence from a quiet baseline, and sufficient history. It ranks research candidates independently of the market-alert score.

Each discovery session nominates no more than ten new candidates. Approximately 20% are quiet comparison securities when suitable candidates are available. Rerunning the same session returns the saved result unless `--force` is supplied.

## Candidate lifecycle

Candidate states are `discovered`, `needs_review`, `approved`, `rejected`, `expired`, `held`, and `archived`. Every transition stores its time, reason, reviewer, and source snapshot.

Only approved candidates enter routine scans. The active universe is capped at 50. Unreviewed nominations expire after ten completed sessions, while their observations and transitions remain available. Weekly revalidation reports identity, listing, price-data, and corporate-action issues without silently changing candidate state.

Every market session captures its approved universe before scanning. Later approvals affect the next uncaptured session and cannot alter a historical replay.

## Market activity score

`activity-v2` compares the current session with prior-session baselines. The current bar is excluded from its own baseline.

| Rule | Threshold | Points |
|---|---:|---:|
| Volume z-score | 2 | 20 |
| Volume z-score | 3 | 10 |
| Relative volume | 3 | 15 |
| Daily return | 10% | 20 |
| Daily return | 20% | 10 |
| Return z-score | 2 | 15 |
| Opening gap | 5% | 10 |
| Intraday range | 10% | 10 |

Two additional joint rules bring the maximum to 130 points. An alert requires a score strictly greater than 50. The stored explanation records every observed feature, threshold, and awarded component.

## Fixed-session outcomes

The alert session is session zero. The next ten exchange sessions form the evaluation horizon. A record remains provisional until the entry bar and all ten future session bars are valid.

A final outcome is `sharp_reversal` when any of these conditions holds:

- Session 1 return is below -10%.
- Session 5 return is below -15%.
- Session 10 return is below -20%.
- The worst closing return through session 10 is below -25%.
- Session 5 is above +5% and session 10 is below -5%.

Otherwise, `sustained_gain` requires returns above +5% at sessions 5 and 10. Other mature records are `mixed`. These categories describe price paths rather than manipulation findings.

Successful observations and finalized outcomes are immutable for a ticker, session, and score version. A separate workspace or new version is required to evaluate changed rules.

## Social evidence

Social evidence is accepted through validated, permitted JSON exports. There is no live collector. Each record preserves source, query scope, publication time, collection time, import time, evidence URL, resolution method, and coverage status.

Supported coverage states are `complete`, `not_collected`, `unavailable`, and `failed`. Only a fully covered query interval with no resolved posts is a confirmed zero. Four complete preceding windows are required for a baseline.

`social-attention-experimental-v1` measures mention growth, unique-author growth, author concentration, repeated text, shared links, and minute-level concentration. It requires at least five current posts, complete current and baseline coverage, a positive baseline, and author identifiers throughout the compared samples. A score of at least 50 is labeled `Elevated attention`.

Social and market scores are never merged. Their joined research labels are:

- `Normal`
- `Elevated social attention`
- `Market anomaly`
- `Combined concern`
- `Insufficient coverage`

## Reproducibility and limitations

Workspaces use atomic file replacement and a single writer lock. Scan attempts retain manifests, input-bar snapshots, hashes, status, timestamps, provider mode, and rule versions. This design is intended for one local writer. Concurrent or high-volume collection should use transactional storage.

The current rules have not established predictive advantage. Reliable evaluation requires prospective alerts, fixed outcomes, quiet comparisons, adequate coverage, and chronological comparisons with simple baselines. Machine learning should only be considered after enough reviewed prospective events exist to evaluate it honestly.
