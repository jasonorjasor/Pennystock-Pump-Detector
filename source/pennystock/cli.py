import argparse
from pathlib import Path
from .storage import DEFAULT_WORKSPACE, ROOT
from .pipeline import scan, track, import_legacy, demo, report


def daily(workspace=DEFAULT_WORKSPACE, session=None, prices_dir=None, watchlist=None):
    """Run the routine workflow and report partial coverage as one result."""
    import json
    from .discovery import initialize_registry, list_candidates
    from .research import research_readiness
    from .pipeline import utcnow
    from .storage import atomic_text, save_json, writer_lock
    started = utcnow()
    initialize_registry(workspace, watchlist or ROOT / "source/MAIN/watchlist.txt")
    scan_result = scan(workspace, session=session, watchlist=watchlist, mode="approved", prices_dir=prices_dir)
    track_result = track(workspace, as_of=session, prices_dir=prices_dir)
    readiness = research_readiness(workspace)
    partial = scan_result["state"] == "partial" or track_result["state"] == "partial"
    candidates = list_candidates(workspace, "needs_review")
    social_failures = sum(r["coverage_status"] not in {"complete", "not_collected"} for r in readiness["rows"])
    result = {"state": "partial" if partial else "complete", "scan": scan_result,
            "tracking": track_result, "readiness": readiness,
            "briefing": str(Path(workspace) / "briefing.md")}
    job = {"kind": "daily", "started_at": started, "finished_at": utcnow(), "state": result["state"],
           "session": scan_result["session"], "score_version": scan_result["score_version"],
           "attempt_id": scan_result["attempt_id"], "errors": scan_result.get("counts", {}).get("fetch_failed", 0)}
    with writer_lock(workspace):
        path = Path(workspace) / "daily_jobs.json"
        jobs = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not any(r["attempt_id"] == job["attempt_id"] for r in jobs):
            jobs.append(job)
            save_json(path, jobs)
        summary = json.loads((Path(workspace) / "summary.json").read_text(encoding="utf-8"))
        atomic_text(Path(workspace) / "briefing.md", "# Microcap Observatory daily briefing\n\n"
            f"Session: {scan_result['session']}\n\nScan coverage: {scan_result['state']} {scan_result.get('counts', {})}\n\n"
            f"Recorded alerts: {summary['total']}\n\nPending outcomes: {summary['pending']}\n\n"
            f"Candidates awaiting review: {len(candidates)}\n\nSocial coverage failures: {social_failures}\n\n"
            "Scores describe unusual evidence; they are not fraud probabilities or investment advice.\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Microcap Observatory: completed-session research")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("scan", help="Scan once and record all ticker statuses")
    s.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    s.add_argument("--session", help="YYYY-MM-DD; defaults to latest completed NYSE session")
    s.add_argument("--historical-run", type=Path)
    s.add_argument("--watchlist", type=Path, default=ROOT / "source/MAIN/watchlist.txt")
    s.add_argument("--watchlist-mode", dest="mode", choices=["approved", "union_selected", "union_tier1", "override"], default="approved")
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
    u = sub.add_parser("universe-init", help="Preserve watchlist candidates as unverified research records")
    u.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    u.add_argument("--watchlist", type=Path, default=ROOT / "source/MAIN/watchlist.txt")
    us = sub.add_parser("universe-update", help="Record a candidate revision with its reason and evidence")
    us.add_argument("ticker")
    us.add_argument("--reason", required=True)
    us.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    us.add_argument("--membership", choices=["research", "archived"], default="research")
    us.add_argument("--issuer")
    us.add_argument("--venue")
    us.add_argument("--security-status", choices=["unverified", "active", "inactive"], default="unverified")
    us.add_argument("--validation-source")
    us.add_argument("--data-availability", default="unknown")
    us.add_argument("--notes")
    si = sub.add_parser("social-import", help="Import a permitted JSON evidence export")
    si.add_argument("source", type=Path)
    si.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    si.add_argument("--profile", choices=["subreddit-export"])
    sf = sub.add_parser("social-features", help="Record a retrospective attention evaluation")
    sf.add_argument("ticker")
    sf.add_argument("source")
    sf.add_argument("--end", required=True, help="Timezone-aware ISO window end")
    sf.add_argument("--window", choices=["1h", "6h", "24h", "7d"], default="24h")
    sf.add_argument("--query-scope")
    sf.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    sd = sub.add_parser("social-demo", help="Create a separate fictional social evidence demo")
    sd.add_argument("--workspace", type=Path)
    rr = sub.add_parser("research-readiness", help="Read-only listing and social evidence readiness report")
    rr.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    rr.add_argument("--as-of", help="Timezone-aware report cutoff; defaults to now")
    rr.add_argument("--window", choices=["1h", "6h", "24h", "7d"], default="24h")
    dy = sub.add_parser("daily", help="Run approved-universe scan, tracking, readiness, and briefing")
    dy.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    dy.add_argument("--session")
    dy.add_argument("--prices-dir", type=Path)
    dy.add_argument("--watchlist", type=Path, default=ROOT / "source/MAIN/watchlist.txt")
    di = sub.add_parser("discover", help="Rank low-priced listed securities for human review")
    di.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    di.add_argument("--session")
    di.add_argument("--max-price", type=float, default=5.0)
    di.add_argument("--symbols-dir", type=Path, help="Offline nasdaq.txt and other.txt directory")
    di.add_argument("--prices-dir", type=Path)
    di.add_argument("--max-new", type=int, default=10)
    di.add_argument("--force", action="store_true", help="Repeat discovery for an already recorded session")
    c = sub.add_parser("candidates", help="List or change candidate review state")
    cs = c.add_subparsers(dest="candidate_command", required=True)
    cl = cs.add_parser("list")
    cl.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    cl.add_argument("--state", dest="state_filter", choices=["discovered", "needs_review", "approved", "rejected", "expired", "held", "archived"])
    for action in ("approve", "reject", "hold", "archive"):
        cp = cs.add_parser(action)
        cp.add_argument("ticker")
        cp.add_argument("--reason", required=True)
        cp.add_argument("--reviewer", default="project-owner")
        cp.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    cr = cs.add_parser("revalidate")
    cr.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    cr.add_argument("--as-of")
    sn = sub.add_parser("social-nominate", help="Nominate one eligible elevated social evaluation for review")
    sn.add_argument("evaluation_id")
    sn.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    try:
        from .history import backtest, analyze_existing
        from .social import universe_init, universe_update, social_import, social_features, social_demo
        from .research import research_readiness
        if command == "candidates":
            from .discovery import change_candidate, list_candidates, revalidate
            action = args.pop("candidate_command")
            if action == "list":
                result = list_candidates(**args)
            elif action == "revalidate":
                result = revalidate(**args)
            else:
                state = {"approve": "approved", "reject": "rejected", "hold": "held", "archive": "archived"}[action]
                result = change_candidate(new_state=state, **args)
        else:
            from .discovery import discover, nominate_from_social
            result = {"scan": scan, "track": track, "import-legacy": import_legacy,
                  "backtest": backtest, "analyze": analyze_existing, "demo": demo, "report": report,
                  "universe-init": universe_init, "social-import": social_import,
                  "universe-update": universe_update,
                  "social-features": social_features, "social-demo": social_demo,
                  "research-readiness": research_readiness, "daily": daily,
                  "social-nominate": nominate_from_social,
                  "discover": discover}[command](**args)
    except ModuleNotFoundError as exc:
        parser.exit(2, "Error: Missing project dependency " + str(exc) +
                    ". Run .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt -c requirements-tested.txt, then use .\\.venv\\Scripts\\python.exe.\n")
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    print(result)
    return 1 if isinstance(result, dict) and result.get("state") == "partial" else 0
