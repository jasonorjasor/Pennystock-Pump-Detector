"""Prospective study registration, simple baselines, and time-gated evaluation."""
import json
from pathlib import Path

import pandas as pd

from . import SCORE_VERSION, OUTCOME_VERSION, THRESHOLD
from .calendar import completed_session, sessions_between, outcome_sessions
from .core import outcome_from_bars
from .pipeline import fetch_bars, utcnow
from .storage import read_csv, save_csv, save_json, writer_lock

STUDY_VERSION = "prospective-12w-v1"
GATES = ((10, "2_week_health"), (30, "6_week_operations"), (60, "12_week_evaluation"))


def ensure_study(workspace, session):
    workspace, day = Path(workspace), completed_session(session)
    path = workspace / "study.json"
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        frozen = state["frozen_rules"]
        current = {"market_score_version": SCORE_VERSION, "outcome_version": OUTCOME_VERSION,
                   "threshold": THRESHOLD, "study_version": STUDY_VERSION}
        if frozen != current:
            raise ValueError("Study rules changed; use a new workspace rather than rewriting the registered study")
        return state
    state = {"study_version": STUDY_VERSION, "started_session": str(day.date()),
             "target_sessions": 60, "target_weeks": 12,
             "frozen_rules": {"market_score_version": SCORE_VERSION, "outcome_version": OUTCOME_VERSION,
                              "threshold": THRESHOLD, "study_version": STUDY_VERSION},
             "gates": [{"session_count": n, "name": name} for n, name in GATES],
             "registered_at": utcnow()}
    with writer_lock(workspace):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        save_json(path, state)
    return state


def record_baselines(workspace, session):
    """Freeze one volume-only and one largest-gainer selection per completed session."""
    workspace, day = Path(workspace), completed_session(session)
    obs = read_csv(workspace / "observations.csv")
    if obs.empty:
        return []
    current = obs[(obs.session.astype(str) == str(day.date())) & obs.scan_status.isin(["alert", "no_signal"])].copy()
    if current.empty:
        return []
    selected = []
    for baseline, column in (("volume_only_v1", "vol_ratio"), ("largest_gainer_v1", "daily_return")):
        row = current.sort_values([column, "ticker"], ascending=[False, True]).iloc[0]
        selected.append({"ticker": row.ticker, "session": str(day.date()), "baseline": baseline,
                         "selected_value": float(row[column]), "selected_at": utcnow(),
                         "state": "provisional", "outcome": "pending"})
    path = workspace / "baseline_outcomes.csv"
    with writer_lock(workspace):
        old = read_csv(path)
        combined = pd.concat([old, pd.DataFrame(selected)], ignore_index=True) if not old.empty else pd.DataFrame(selected)
        combined = combined.drop_duplicates(["ticker", "session", "baseline"], keep="first")
        save_csv(path, combined)
    return selected


def track_baselines(workspace, as_of=None, prices_dir=None):
    workspace, day = Path(workspace), completed_session(as_of)
    path = workspace / "baseline_outcomes.csv"
    frame = read_csv(path)
    if frame.empty:
        return {"state": "complete", "updates": 0}
    rows, partial, changed = frame.to_dict("records"), False, False
    for row in rows:
        if row.get("state") == "final" or pd.Timestamp(row["session"]) > day:
            continue
        try:
            expected = outcome_sessions(row["session"])
            bars = fetch_bars(row["ticker"], row["session"], min(day + pd.Timedelta(days=1), expected[-1] + pd.Timedelta(days=1)), prices_dir)
            result = outcome_from_bars(bars, row["session"], expected, day)
            if result["data_status"] in {"complete", "awaiting_sessions"}:
                row.update(result, as_of=str(day.date()), updated_at=utcnow())
                changed = True
            else:
                partial = True
        except Exception as exc:
            row["last_error"] = f"{type(exc).__name__}: {exc}"
            partial = True
    if changed:
        with writer_lock(workspace):
            latest = read_csv(path)
            key = lambda row: (row["ticker"], str(row["session"]), row["baseline"])
            merged = {key(row): row for row in latest.to_dict("records")}
            for row in rows:
                old = merged.get(key(row))
                if not old or old.get("state") != "final":
                    merged[key(row)] = row
            save_csv(path, pd.DataFrame(merged.values()))
    return {"state": "partial" if partial else "complete", "updates": sum(r.get("updated_at") is not None for r in rows)}


def study_report(workspace, as_of=None):
    workspace = Path(workspace)
    study_path = workspace / "study.json"
    if not study_path.exists():
        return {"registered": False, "study_version": STUDY_VERSION, "completed_sessions": 0,
                "target_sessions": 60, "next_gate": {"session_count": 10, "name": "2_week_health"},
                "coverage": None, "cohorts": [], "machine_learning_eligible": False}
    state = json.loads(study_path.read_text(encoding="utf-8"))
    day = completed_session(as_of)
    start = pd.Timestamp(state["started_session"])
    elapsed = len(sessions_between(start, day))
    alerts = read_csv(workspace / "alerts.csv")
    baselines = read_csv(workspace / "baseline_outcomes.csv")
    if not alerts.empty:
        alerts = alerts[pd.to_datetime(alerts.session).between(start, day)]
    if not baselines.empty:
        baselines = baselines[pd.to_datetime(baselines.session).between(start, day)]
    def cohort(frame, label):
        if frame.empty:
            return {"cohort": label, "selected": 0, "final": 0, "sharp_reversals": 0, "reversal_share": None}
        final = frame[frame.get("state", pd.Series(index=frame.index, dtype=str)).eq("final")]
        reversals = int(final.get("outcome", pd.Series(dtype=str)).eq("sharp_reversal").sum())
        return {"cohort": label, "selected": len(frame), "final": len(final), "sharp_reversals": reversals,
                "reversal_share": reversals / len(final) if len(final) else None}
    cohorts = [cohort(alerts, "market_score")]
    if not baselines.empty:
        cohorts += [cohort(group, name) for name, group in baselines.groupby("baseline")]
    observations = read_csv(workspace / "observations.csv")
    if not observations.empty:
        observations = observations[pd.to_datetime(observations.session).between(start, day)]
    coverage = None if observations.empty else float(observations.scan_status.isin(["alert", "no_signal"]).mean())
    return {"registered": True, "study_version": STUDY_VERSION, "started_session": state["started_session"],
            "as_of": str(day.date()), "completed_sessions": elapsed, "target_sessions": state["target_sessions"],
            "next_gate": next(({"session_count": n, "name": name} for n, name in GATES if elapsed < n), None),
            "coverage": coverage, "cohorts": cohorts,
            "machine_learning_eligible": cohorts[0]["final"] >= 100}
