# Data formats

Generated workspaces live under `runs/` and are excluded from Git. JSON files use UTF-8, ISO 8601 timestamps, explicit schema or score versions, and UTC for social-event normalization.

## Market workspace

| Path | Contents |
|---|---|
| `workspace.json` | Workspace kind, schema version, score version, and provider mode |
| `observations.csv` | Ticker/session observations and explicit scan status |
| `outcomes.csv` | Provisional and final ten-session outcomes |
| `alerts.csv` | Derived alert and outcome export |
| `summary.json` | Cohort metrics |
| `briefing.md` | Generated daily briefing |
| `latest_scan.json` | Latest scan manifest, universe, coverage, and counts |
| `latest_tracking.json` | Latest outcome-update manifest |
| `daily_jobs.json` | Daily job attempts and completion status |
| `study.json` | Registered study start, frozen rule versions, and evaluation gates |
| `baseline_outcomes.csv` | Prospective volume-only and largest-gainer selections and fixed outcomes |
| `notes.json` | Local observation notes and evidence links |
| `attempts/<id>/` | Attempt manifest, archived bars, hashes, and per-ticker results |

The natural key for a market observation or outcome is ticker, session, and score version. The first successful observation and finalized outcome under that key are preserved.

## Candidate registry

`candidates.json` contains these record groups:

- `identities`: symbol, issuer, venue, security type, directory status, listing deficiency, source, and retrieval time
- `candidates`: current state, first-seen time, latest transition time, reason, reviewer, and quiet-comparison flag
- `transitions.review`: identity/liquidity checks, catalyst category, corporate-action status, data quality, and optional evidence URL for human decisions
- `transitions`: prior state, new state, timestamp, reason, reviewer, and source snapshot
- `discovery_runs`: session, configuration, score version, coverage counts, and status
- `observations`: ticker, as-of time, market features, discovery score, collection status, and context flags
- `universe_snapshots`: approved tickers captured for a market session
- `revalidation_runs`: dated identity and data-health reviews

`approved_watchlist.txt` is a generated newline-delimited export of approved symbols. `source/MAIN/watchlist.txt` remains a local manual seed or override. `source/MAIN/watchlist.example.txt` is the shareable template.

## Social import schema

Imports are limited to 10 MB with at most 10,000 observations and 10,000 coverage records. The entire payload is validated before anything is saved.

```json
{
  "schema_version": 1,
  "data_kind": "research",
  "observations": [
    {
      "source": "reddit:example-community",
      "query_scope": "cashtag:DEMO",
      "source_post_id": "example-1",
      "url": "https://www.reddit.com/r/example/comments/example-1",
      "published_at": "2026-09-10T17:55:00Z",
      "collected_at": "2026-09-10T18:00:00Z",
      "raw_ticker_text": "$DEMO",
      "text": "$DEMO example observation",
      "author_id": "source-author-id",
      "language": "en",
      "engagement": {"score": 3}
    }
  ],
  "coverage": [
    {
      "source": "reddit:example-community",
      "ticker": "DEMO",
      "query_scope": "cashtag:DEMO",
      "start": "2026-09-09T18:00:00Z",
      "end": "2026-09-10T18:00:00Z",
      "collected_at": "2026-09-10T18:00:00Z",
      "status": "complete"
    }
  ]
}
```

Required observation fields are `source`, `query_scope`, `source_post_id`, `url`, `published_at`, `collected_at`, and `text`. Optional fields are `raw_ticker_text`, `author_id`, `language`, and `engagement`.

Required coverage fields are `source`, `ticker`, `query_scope`, `start`, `end`, `collected_at`, and `status`. Valid statuses are `complete`, `not_collected`, `unavailable`, and `failed`; an optional `error` may describe collection failure.

Publication time must not exceed collection time. Collection time must not exceed import time. All timestamps require a timezone.

Posts are deduplicated by source, source post ID, and query scope. Conflicting content under the same identity rejects the batch. Normalized storage keeps a salted author hash rather than the supplied raw author identifier. Ambiguous and multi-ticker posts remain available for review but are excluded from ticker scores.

## Local-only files

The following are excluded from Git:

- Personal watchlists and approved-universe exports
- Market and social research workspaces
- Imported source exports
- Notes and evidence collections
- Provider caches
- SQLite databases and journals
- Credentials, environment files, and private keys
- IDE, agent, and local planning files

Synthetic fixtures intended for automated tests remain under `tests/`.
