# Research workflow and next steps

## Plan executed

The plan was shown before editing: expose missing prerequisites, create a dated attention review queue, add dashboard import previews, and verify old/new workflows. These features are now implemented. The report against the existing local registry found 12 candidates needing listing review and no imported social coverage. It did not independently verify any listing.

## Use it

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard/dashboard.py
```

Open **Social evidence** in an Observatory workspace:

1. **Research readiness** shows listing reminders, query coverage, baseline status, and next actions. Coverage is checked through the current UTC time; an old successful collection does not look current. The 30-day listing reminder is a project policy, not a regulatory standard. Listing status remains a user-recorded assertion.
2. **Import social evidence** accepts a permitted JSON export in the [documented format](SOCIAL_EVIDENCE.md). Preview reports new records, sources, resolved tickers, and unresolved total without saving. **Save validated import** revalidates against current state under the writer lock. Duplicate-only imports need no save. The original upload is not written to disk; the limit is 10 MB.
3. Select a ticker/query/window and inspect the score. **Record this evaluation** saves the actual generation time, including insufficient-data results. Simply viewing the page does not write evaluations.
4. **Attention review queue** shows the latest recorded elevated evaluation per ticker/source/query/window/score version. A later normal or insufficient-data evaluation supersedes an older concern. Re-running an older window does not displace a newer window. Archived candidates are excluded.
5. Enter what you found and mark an evaluation reviewed. This appends a dated note and preserves the score. Reviewed entries can be shown again. New evidence relevant to the scored interval or baseline is flagged for re-evaluation.

The queue is a view of recorded evaluations, not a live feed. Windows older than their own duration are labeled historical. Recent windows are still retrospective import analysis. A quiet queue does not establish complete coverage or absence of suspicious activity.

```powershell
# Read-only report; defaults to the current time and a 24-hour window.
python observatory.py research-readiness
python observatory.py research-readiness --workspace runs/social_demo --as-of 2025-11-07T18:00:00Z
```

The report uses the current registry and imported evidence even with an older cutoff; it is not an as-known-then backtest. Reviews remain in the ignored `social.json`. Synthetic imports are rejected in the default research workspace. Market scores, outcomes, and the personal watchlist remain unchanged.

## Streamlit decision

**Retain Streamlit for the local research application.** This is an engineering judgment based on the existing Python services and working dashboard. A frontend rewrite would not improve data coverage or establish signal quality.

Streamlit provides forms, session state, caching, and rerun controls. Its server must support concurrent-user resource needs, and distributed deployment has session-affinity considerations. [Execution model](https://docs.streamlit.io/develop/concepts/architecture), [client/server architecture](https://docs.streamlit.io/develop/concepts/architecture/architecture).

| Need | Direction |
|---|---|
| Local evidence tables, charts, exploration, manual review | Continue Streamlit |
| Scheduled collection and evaluation | Independent jobs calling shared Python services |
| Public product, detailed account permissions, highly customized interactions | Reassess a dedicated frontend/backend once requirements are concrete |
| Large histories and concurrent writers | Improve indexed storage and transactions before scaling the UI |

Readiness, queue, and import validation live outside Streamlit and can support a future interface. The current file store's scaling limitations are separate from the frontend choice.

## API access findings

Checked September 9, 2026. The user confirmed no approved API/data-feed access is available. No account was created, request submitted, purchase made, or live collector connected.

| Source | Finding and next action |
|---|---|
| Reddit | Explicit API approval is required; research is directed to Reddit for Researchers. Eligibility for this personal project is not established. Ask which approved route fits the actual use; do not claim academic affiliation or moderation status. [Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy) |
| Stocktwits | The developer page says new registrations are paused. Confirm a supported offering before designing a connector. [Developer page](https://api.stocktwits.com/developers) |
| X | Official documentation describes usage-based pricing and credits. Review access, intended-use terms, and a spending limit before paid calls. [Pricing](https://docs.x.com/x-api/getting-started/pricing) |
| Bluesky | The official search specification allows authentication requirements and warns pagination may not expose all results. It is a candidate for a bounded experiment, not a verified free source of complete ticker counts. [Official specification](https://github.com/bluesky-social/atproto/blob/main/lexicons/app/bsky/feed/searchPosts.json) |

A public Bluesky search request could not be verified through the browsing tool. That is a verification limitation, not evidence that the service is down. Search completeness and timestamp semantics require testing before supporting the baseline score.

The assistant can prepare requests and implement/test a connector once suitable access exists. Account identity, provider approval, and any payment remain with the user/provider. A local draft request is kept in the ignored planning directory.

## Following milestones and why

1. **Validate the research candidates.** Check current symbols, issuer identities, venues, corporate changes, and data availability with dated authoritative sources. This prevents monitoring stale identities. Preserve historical records.
2. **Obtain one suitable source.** Confirm permitted use, coverage, costs, and retention/deletion requirements. Choose based on useful evidence rather than API availability alone.
3. **Build one bounded collector.** Record pagination, failures, source time, actual receipt time, and deletion/expiry behavior. Partial search results must not become complete coverage.
4. **Record prospective evaluations.** Build sufficient baseline history, freeze evaluations at generation time, then compare them with later market observations and fixed-session outcomes. This makes warning lead time measurable.
5. **Evaluate usefulness before expansion.** Measure reviewed relevance, false alarms, coverage, and lead time on chronologically separated data. Tune rules or add sources when measurements identify a specific gap.

The target is a smaller, well-evidenced research queue with measured limitations. No milestone assumes proof of manipulation or profitable trading.
