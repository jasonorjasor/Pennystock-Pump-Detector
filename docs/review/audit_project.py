"""Offline review evidence. Reads existing artifacts; never runs pipeline entrypoints.

Run from any directory: python <project>/docs/review/audit_project.py
Writes only audit_evidence.json next to this script.
"""
import ast
import contextlib
import io
import json
import subprocess
from collections import Counter
from pathlib import Path
from datetime import datetime, timedelta
from math import sqrt
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "runs/2025-11-07_2227_1y"
BASELINE_COMMIT = "6d21d5171292d1615a33e0dbf9cdf1c21e1fc1f3"


def extract(relative, names, namespace):
    # Review reproductions intentionally target the pre-release implementation.
    # The current entrypoints now call the repaired engine.
    source = subprocess.check_output(
        ["git", "show", f"{BASELINE_COMMIT}:{relative}"], cwd=ROOT, encoding="utf-8")
    tree = ast.parse(source)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(nodes) == len(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), relative, "exec"), namespace)
    return namespace


def main():
    files = list((ROOT / "source").rglob("*.py")) + list((ROOT / "dashboard").rglob("*.py"))
    for path in files:
        ast.parse(path.read_text(encoding="utf-8-sig"))
    evidence = {"review_date": "2026-09-09", "syntax_parsed": [str(p.relative_to(ROOT)) for p in files]}
    evidence["artifact_counts"] = dict(Counter(p.suffix for p in RUN.rglob("*") if p.is_file()))
    a = pd.read_csv(RUN / "data/alerts/alerts_history.csv", parse_dates=["alert_date"])
    classified = a[a.outcome.ne("pending")]
    evidence["alerts"] = {
        "rows": len(a), "tickers": a.ticker.nunique(), "outcomes": a.outcome.value_counts().to_dict(),
        "first_date": str(a.alert_date.min().date()), "last_date": str(a.alert_date.max().date()),
        "duplicate_ticker_dates": int(a.duplicated(["ticker", "alert_date"]).sum()),
        "tiers": a.tier.value_counts().to_dict(),
        "precision_pct": 100 * classified.outcome.isin(["confirmed_pump", "likely_pump"]).mean(),
        "all_alert_denominator_pct": 100 * a.outcome.isin(["confirmed_pump", "likely_pump"]).mean(),
        "bottom_over_30_calendar_days": int(a.days_to_bottom.gt(30).sum()),
        "max_days_to_bottom": float(a.days_to_bottom.max()),
        "scores_above_dashboard_bin_cap": int(a.pump_score.gt(120).sum()),
        "top_tickers": a.ticker.value_counts().head(5).to_dict(),
    }
    snapshots = sorted((RUN / "daily_snapshots").glob("*.json"))
    evidence["latest_snapshot"] = json.loads(snapshots[-1].read_text())
    bad_json = []
    for p in RUN.rglob("*.json"):
        try:
            json.loads(p.read_text())
        except (ValueError, UnicodeError):
            bad_json.append(str(p.relative_to(ROOT)))
    evidence["unreadable_json"] = bad_json
    csv_errors = []
    for p in RUN.rglob("*.csv"):
        try:
            pd.read_csv(p)
        except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
            csv_errors.append({"file": str(p.relative_to(ROOT)), "error": str(exc)})
    evidence["unreadable_csv"] = csv_errors
    daily = []
    for p in sorted((RUN / "data/alerts").glob("pump_alerts_*.csv")):
        d = pd.read_csv(p)
        duplicates = int(d.duplicated(["ticker", "alert_date"]).sum())
        if duplicates:
            daily.append({"file": p.name, "rows": len(d), "duplicate_rows": duplicates})
    evidence["daily_files_with_duplicates"] = daily
    master = pd.read_csv(RUN / "data/signals_csv/MASTER_TRUTH_WITH_EPISODES.csv")
    eps = pd.read_csv(RUN / "data/signals_csv/PUMP_EPISODES.csv")
    evidence["historical"] = {"signals": len(master), "tickers": master.ticker.nunique(),
        "outcomes": master.classification.value_counts().to_dict(), "episodes": len(eps),
        "episodes_without_pump_labels": int(eps.pump_count.eq(0).sum())}

    ns = extract("source/MAIN/alert_tracker.py", ["get_forward_returns_cached", "classify_outcome", "generate_markdown_report", "wilson_ci"],
                 {"pd": pd, "np": np, "datetime": datetime, "timedelta": timedelta, "sqrt": sqrt})
    dates = pd.bdate_range("2025-01-02", periods=45)
    df = pd.DataFrame({"Close": [10] + [11] * 39 + [6] * 5}, index=dates)
    early = ns["get_forward_returns_cached"]("TEST", dates[0], 10, [1, 5, 10], {"TEST": df.iloc[:21]})
    late = ns["get_forward_returns_cached"]("TEST", dates[0], 10, [1, 5, 10], {"TEST": df})
    evidence["reproductions"] = {"unbounded_outcome": {
        "early": ns["classify_outcome"](early), "late": ns["classify_outcome"](late),
        "same_1_5_10_returns": all(early[f"return_{d}d"] == late[f"return_{d}d"] for d in [1, 5, 10]),
        "late_days_to_bottom": late["days_to_bottom"]}}
    assert evidence["reproductions"]["unbounded_outcome"]["early"] == "false_positive"
    assert evidence["reproductions"]["unbounded_outcome"]["late"] == "confirmed_pump"
    # Strip no values: this measures dependency on the unbounded drawdown field,
    # NOT the corrected fixed-horizon success rate.
    changed = []
    for _, row in a.iterrows():
        old = ns["classify_outcome"](row)
        candidate = row.copy()
        candidate["max_drawdown"] = np.nan
        if old != ns["classify_outcome"](candidate):
            changed.append({"ticker": row.ticker, "date": str(row.alert_date.date()), "days_to_bottom": row.days_to_bottom})
    evidence["labels_dependent_on_drawdown_field"] = changed
    # A single ticker batch can retain ticker-first MultiIndex columns.
    multi = df.iloc[:12].copy()
    multi.columns = pd.MultiIndex.from_tuples([("TEST", "Close")])
    try:
        ns["get_forward_returns_cached"]("TEST", dates[0], 10, [1, 5, 10], {"TEST": multi})
    except KeyError as exc:
        evidence["reproductions"]["single_ticker_multiindex"] = str(exc)
    # All-pending report fails before any write. Fake filesystem prevents side effects.
    class NoWriteOS:
        @staticmethod
        def makedirs(*args, **kwargs):
            pass
    ns.update({"os": NoWriteOS, "WEEKLY_REVIEWS_DIR": "unused"})
    pending = a.iloc[:1].copy()
    pending["outcome"] = "pending"
    try:
        ns["generate_markdown_report"](pending)
    except TypeError as exc:
        evidence["reproductions"]["all_pending_report"] = str(exc)
    intervals = pd.read_csv(RUN / "data/analysis/ticker_intervals.csv")
    scan = extract("source/MAIN/tiered_scanner.py", ["assign_tiers", "run_scan", "calculate_pump_score"],
                   {"pd": pd, "np": np, "datetime": datetime, "TIER1_MIN_EPISODES": 6, "TIER2_MIN_EPISODES": 4})
    tiers = scan["assign_tiers"](intervals)
    calls = []
    scan.update({"WATCHLIST_OVERRIDE": (ROOT / "source/MAIN/watchlist.txt").read_text().split(),
        "WATCHLIST_MODE": "union_tier1", "tiers": tiers, "intervals_df": intervals,
        "last_pump_dates": {}, "check_ticker": lambda ticker, tier, *args: calls.append((ticker, tier))})
    with contextlib.redirect_stdout(io.StringIO()):
        scan["run_scan"](["tier1", "tier2"])
    checked = {t for t, _ in calls}
    evidence["reproductions"]["scan_universe"] = {"calls": len(calls), "unique_tickers": len(checked),
        "missing_tier2": sorted(set(tiers["tier2"]) - checked), "assigned_tiers": tiers}
    changed_scores = changed_flags = total_bars = 0
    for path in (RUN / "data/signals_csv").glob("*/signals.csv"):
        raw = pd.read_csv(path)
        scored = scan["calculate_pump_score"](raw)
        changed_scores += int(scored.pump_score.ne(raw.pump_score).sum())
        changed_flags += int(scored.pump_score.gt(50).ne(raw.pump_score.gt(50)).sum())
        total_bars += len(raw)
    evidence["live_formula_on_saved_bars"] = {"bars": total_bars, "changed_scores": changed_scores, "changed_alert_flags": changed_flags}
    target = Path(__file__).with_name("audit_evidence.json")
    target.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    print(json.dumps(evidence, indent=2, default=str))


if __name__ == "__main__":
    main()
