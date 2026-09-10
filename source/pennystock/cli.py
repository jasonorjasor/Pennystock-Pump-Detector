import argparse
from pathlib import Path
from .storage import DEFAULT_WORKSPACE, ROOT
from .pipeline import scan, track, import_legacy, demo, report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Microcap Observatory: completed-session research")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("scan", help="Scan once and record all ticker statuses")
    s.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    s.add_argument("--session", help="YYYY-MM-DD; defaults to latest completed NYSE session")
    s.add_argument("--historical-run", type=Path)
    s.add_argument("--watchlist", type=Path, default=ROOT / "source/MAIN/watchlist.txt")
    s.add_argument("--watchlist-mode", dest="mode", choices=["union_selected", "union_tier1", "override"], default="union_selected")
    s.add_argument("--prices-dir", type=Path, help="Offline OHLCV: TICKER.csv or TICKER/signals.csv")
    t = sub.add_parser("track", help="Update provisional outcomes; finalized outcomes stay frozen")
    t.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    t.add_argument("--as-of", help="Completed session cutoff")
    t.add_argument("--prices-dir", type=Path)
    i = sub.add_parser("import-legacy", help="Import alerts into a separate reconstruction workspace")
    i.add_argument("source", type=Path)
    i.add_argument("--workspace", type=Path, required=True)
    b = sub.add_parser("backtest", help="Create a new historical run with shared v2 rules")
    b.add_argument("--start")
    b.add_argument("--end")
    b.add_argument("--tickers", nargs="+")
    b.add_argument("--prices-dir", type=Path)
    b.add_argument("--run-name")
    a = sub.add_parser("analyze", help="Refresh descriptive episodes in a v2 historical run")
    a.add_argument("--run", type=Path)
    d = sub.add_parser("demo", help="Offline demo: local archived bars or fictional data on a fresh clone")
    d.add_argument("--workspace", type=Path)
    r = sub.add_parser("report", help="Read the current cohort metrics without downloads")
    r.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    try:
        from .history import backtest, analyze_existing
        result = {"scan": scan, "track": track, "import-legacy": import_legacy,
                  "backtest": backtest, "analyze": analyze_existing, "demo": demo, "report": report}[command](**args)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    print(result)
    return 1 if isinstance(result, dict) and result.get("state") == "partial" else 0
