# Social evidence foundation

See the [research workflow guide](RESEARCH_WORKFLOW.md) for dashboard import previews, readiness reports, recorded attention queues, and dated review notes.

The product direction is an explainable research queue: identify unusual public attention, inspect its sources alongside market observations, and eventually measure whether recorded warnings precede reversals. This release implements the local evidence foundation. It does **not** establish predictive accuracy, determine manipulation, or collect live social feeds.

## Why this part of the plan is useful

FINRA describes stock promotion through social media and private messaging, including exchange-listed small-cap targets. That supports collecting promotion evidence alongside market activity, while recognizing that public feeds cannot see every channel. Popularity and rising prices alone do not establish wrongdoing. [FINRA: Avoiding Pump-and-Dump Scams](https://www.finra.org/investors/insights/pump-and-dump-scams).

Research using online stock forums suggests that social information can help investigate price/volume events, but identifies difficulties with unobserved discussions and coincidental timing. Its reported classifier performance is not a benchmark for this project's different data and unvalidated heuristic. [Nam and Skillicorn, 2023](https://arxiv.org/abs/2301.11403).

The practical inference is to preserve evidence, query coverage, and timing before attempting ML or claims about warning lead time. Reddit currently requires explicit approval for API access; a working JSON import is a useful first adapter without assuming live access exists. [Reddit Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy).

## Run it

From the repository root, using the existing environment:

```powershell
# Preserve the personal watchlist as research candidates, without asserting current listing status.
.\.venv\Scripts\python.exe observatory.py universe-init

# Create a separate, entirely fictional demonstration. Destination must be empty.
.\.venv\Scripts\python.exe observatory.py social-demo
.\.venv\Scripts\python.exe -m streamlit run dashboard/dashboard.py
```

Select **Observatory / social_demo**, then **Social evidence**. The fictional DEMO ticker has a burst against a quiet baseline and can receive an attention label without any market alert. The demo is not a market replay. Generated example input is `runs/social_demo/example_import.json`.

For your own permitted export, save the file beneath `runs/` so it remains local:

```powershell
.\.venv\Scripts\python.exe observatory.py social-import runs/my_import.json
.\.venv\Scripts\python.exe observatory.py social-features FEMY my_source --end 2026-09-09T18:00:00Z --window 24h --query-scope cashtag:FEMY
```

The evaluation end is exclusive and must include a timezone. Choose the end of your actual collected interval. `social-features` persists an evaluation with the actual generation time; simply viewing the dashboard does not write evaluations. This is retrospective import analysis even when the requested interval is recent.

## Research universe

`universe-init` captures a dated snapshot and SHA-256 of the supplied watchlist. It is idempotent and leaves the watchlist itself untouched. All imported securities start **unverified**, with unknown issuer, venue, and data availability. There is no manufactured 30–50-stock list.

Each candidate records ticker, issuer, venue, research/archived membership, active/inactive/unverified security status, addition/removal timestamps, change reason, validation source and timestamp, availability notes, and version. Every revision is retained in `universe_history`. Archiving a candidate is distinct from asserting that its listing is inactive.

```powershell
python observatory.py universe-update FEMY --membership archived --reason "Paused research pending listing verification"
```

Updates are **complete replacement revisions**, not partial patches: omitted descriptive fields become unknown and status defaults to unverified. Supply all verified metadata you intend to retain. Marking a security active/inactive requires `--validation-source`; the application records your assertion and does not independently verify the cited source.

This research registry does not yet replace the market scanner's watchlist/tier selection. Updating it therefore does not silently change scheduled market coverage. A continuously maintained active-attention list and automated listing/corporate-action validation remain future work.

## JSON adapter contract

Root: `schema_version: 1`, `data_kind: "research" | "synthetic"`, and arrays `observations` and `coverage`. A file is limited to 10 MB and each array to 10,000 records. Validation completes before state is saved; a rejected batch does not partially import.

```json
{
  "schema_version": 1,
  "data_kind": "synthetic",
  "observations": [{
    "source": "fixture",
    "query_scope": "cashtag:DEMO",
    "source_post_id": "example-1",
    "url": "https://example.invalid/posts/example-1",
    "published_at": "2025-11-07T17:55:00Z",
    "collected_at": "2025-11-07T18:00:00Z",
    "raw_ticker_text": "$DEMO",
    "text": "$DEMO fictional observation",
    "author_id": "fictional-author",
    "language": "en",
    "engagement": {"likes": 3}
  }],
  "coverage": [{
    "source": "fixture",
    "ticker": "DEMO",
    "query_scope": "cashtag:DEMO",
    "start": "2025-11-06T18:00:00Z",
    "end": "2025-11-07T18:00:00Z",
    "collected_at": "2025-11-07T18:00:00Z",
    "status": "complete"
  }]
}
```

Optional post fields are `raw_ticker_text`, `author_id`, `language`, and `engagement`. Text may be a permitted excerpt, but truncation affects matching and repetition features. Normalized records add an internal ID, import time, salted author hash, resolved ticker/confidence/method, and collection status. Raw author IDs are not stored in `social.json`; the source import file still contains whatever you supplied.

Deduplication is by source, source post ID, and query scope. A post can belong to separate queries, but each analysis uses exactly one query, preventing cross-query double counting. Reimports keep the first collection time, engagement snapshot, and resolution. Changed content under the same identity rejects the batch instead of overwriting evidence. Universe edits do not retroactively re-resolve old posts.

Resolution uses the post text, not untrusted `raw_ticker_text` metadata. A cashtag is preferred; issuer-plus-exact-ticker context is next. Uppercase symbols of at least four characters have a weaker match, with a small common-word exclusion set. Ambiguous or multi-ticker posts remain stored but unscored. The heuristic can still make errors; it is not a complete ticker language model.

## Coverage and baselines

Coverage statuses are `complete`, `not_collected`, `unavailable`, and `failed`. Missing records mean **not collected**. Only a fully covered interval with zero resolved mentions is a confirmed zero **for that query**. A successful record means the adapter completed the declared query; it is not independently verified platform-wide completeness. Truncated, rate-limited, or sampled retrieval must not be declared complete.

Adjacent successful intervals may cover a window. A failed retry does not erase an already successful collection. Successful recovery can complete a former gap. Query scopes never combine implicitly; change the scope identifier when collection definitions change.

Available windows: 1 hour, 6 hours, 24 hours, and 7 days. The baseline is the four immediately preceding, non-overlapping windows for the same ticker/source/query. All four must have complete coverage. A zero baseline yields `zero_baseline`, not infinite growth; missing intervals yield `insufficient_baseline`.

Features include observed mention count, known unique authors, count/author growth ratios, largest-author share, fraction of posts with exactly repeated normalized text, largest exact shared-link share, and largest UTC-minute share. Links are exact strings, not semantic or tracking-normalized URLs. Minute concentration is a burst proxy, not proof of coordination. Engagement and language are retained but not scored. There is no sentiment model.

## Experimental attention score

| Component | Threshold | Points |
|---|---:|---:|
| Mention growth vs baseline | >= 3x | 30 |
| Unique-author growth vs baseline | >= 2x | 20 |
| Largest author's share of posts | >= 50% | 10 |
| Posts belonging to repeated-text groups | >= 50% | 15 |
| Most common link's share of posts | >= 50% | 10 |
| Most populated minute's share of posts | >= 50% | 15 |

Points require at least five current posts, complete current/baseline coverage, a positive mention baseline, and author identifiers throughout the compared samples. A score of at least 50 labels **Elevated attention**. Below 50 labels **Normal** within the observed query. Missing prerequisites produce an explicit insufficient-data label and null score.

These are initial engineering heuristics, **not calibrated probabilities or research-established thresholds**. The rules live in `social.py` under version `social-attention-experimental-v1`; changing them requires a new version. End-user score configuration is deferred until evaluation provides a reason to tune thresholds. Each evaluation stores component values, thresholds, points, baseline status, and source/query identity. The market activity score and its outcomes remain separate.

## Time, storage, and privacy

`social.json` is a versioned local JSON document updated atomically under the existing writer lock. It contains the universe and revisions, normalized posts, coverage, and evaluations. It is ignored by Git, as are files under `runs/`. This is suitable for small local research batches; it reloads the full document and has no database indexes or pagination. It is not a high-volume ingestion service.

All input timestamps require timezones and normalize to UTC. Publication must precede collection; collection cannot be in the future. The dashboard chronology joins social publications with existing market observation rows at their scan capture times. Evaluations appear at their actual generation times, with their historical window end shown separately. It does not backdate alerts. Coverage intervals are displayed separately from the event table.

Historical calculations use supplied publication/collection times and the currently imported evidence, not a reconstruction of what this application actually knew then. Import time remains visible. Measuring real warning lead time requires prospective collection and frozen evaluations; this release deliberately makes no such claim.

Author hashes are pseudonyms, not anonymization. Text, URLs, and source IDs may still identify people. Import only data you have permission to retain, keep it local, and apply the source's required deletion/retention policy. There is no automatic expiry or per-post deletion synchronization yet. For disposable experiments, remove the whole dedicated social research dataset and original import exports when retention ends; do not keep production feeds running until deletion handling is implemented. The existing single-writer/synced-folder limitations still apply.

## Scope and next step

Implemented: versioned candidates, JSON adapter/validation, deduplication, conservative matching, coverage-aware features, separate explained attention score, persisted retrospective evaluations, an evidence chronology in Streamlit, and an isolated fictional demo.

Deferred: official live collector, automatic listing validation, a continuously refreshed live attention queue, combined-concern classification, interactive aligned price/volume/social charts, news/filing enrichment, HTTP endpoints and pagination, configurable scoring, ML, and prospective lead-time evaluation. The existing local UI calls shared Python services directly; introducing an HTTP server before a consumer needs it would add maintenance without improving this initial research workflow.

The next feature should be **one approved source adapter with coverage and deletion handling**, followed by prospective recording. It should translate an official response into the import contract, identify its query scope, finish pagination before asserting completeness, record failures separately, and keep credentials out of exports. First obtain the provider access that fits the intended use. Then assess coverage and observed false alarms before expanding platforms or tuning the score.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests cover old market workflows plus social import atomicity/idempotence, ambiguity, universe revisions, coverage gaps/zero/recovery boundaries, query isolation, missing authors/baselines, timezones, chronology, and the social dashboard without market alerts. Synthetic examples exercise mechanics only; they are not detector-accuracy validation.
