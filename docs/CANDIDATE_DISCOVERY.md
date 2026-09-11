# Candidate discovery and registry

Candidate discovery is a research-ranking step. It does not label manipulation and it does not add a ticker to routine scanning without review.

## Daily workflow

Always use the project environment on Windows:

```powershell
.\.venv\Scripts\python.exe observatory.py daily
```

This selects the latest completed exchange session, snapshots approved tickers, scans them, updates pending ten-session outcomes, reports readiness, and writes `runs/observatory_v2/briefing.md`. Repeating it preserves one successful observation and one finalized outcome for each ticker, session, and score version.

## Discover and review

```powershell
.\.venv\Scripts\python.exe observatory.py discover
.\.venv\Scripts\python.exe observatory.py candidates list --state needs_review
.\.venv\Scripts\python.exe observatory.py candidates approve TICKER --reason "Verified issuer, venue, and chart"
.\.venv\Scripts\python.exe observatory.py candidates reject TICKER --reason "Ineligible security type"
```

The default price ceiling is $5. Change it with `--max-price`. Discovery uses official Nasdaq Trader listed-symbol directories and yfinance adjusted daily bars. Provider failures remain visible as incomplete coverage and are never scored as ordinary activity.

`discovery-v1` uses prior-session volume, volume ratio, one-day return, median dollar volume, quiet-baseline emergence, and history availability. The stored component values explain every rank. Listing deficiency and possible split or symbol-transition fields remain context.

The registry stores identity snapshots, candidate observations, transitions, discovery runs, and scan-universe snapshots in local `candidates.json`. Approved symbols are exported to local `approved_watchlist.txt`. These research files remain outside Git.

The dashboard's **New candidates** tab displays pending candidates and approve/reject controls. Approval affects the next session that has not already captured a universe snapshot. Historical sessions keep their original universe.

## Offline verification

For reproducible tests or a smoke check, provide official-directory-shaped fixtures named `nasdaq.txt` and `other.txt`, plus ticker CSV files:

```powershell
.\.venv\Scripts\python.exe observatory.py discover --symbols-dir PATH_TO_DIRECTORIES --prices-dir PATH_TO_PRICES --session YYYY-MM-DD
```

Run the full offline suite with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
