"""Read-only readiness reports and a dated queue of recorded social evaluations."""
from datetime import timedelta
from pathlib import Path

from .social import WINDOWS, features, now, read_state, required, timestamp
from .storage import DEFAULT_WORKSPACE, save_json, writer_lock


def readiness(state, as_of=None, window="24h", listing_max_age_days=30):
    """30 days is a review reminder policy, not an exchange or regulatory standard."""
    end = timestamp(as_of or now())
    if window not in WINDOWS:
        raise ValueError("Unsupported social window")
    if type(listing_max_age_days) is not int or listing_max_age_days < 1:
        raise ValueError("listing_max_age_days must be a positive integer")
    rows = []
    for candidate in sorted(state["universe"], key=lambda r: r["ticker"]):
        if candidate["membership"] != "research":
            continue
        ticker = candidate["ticker"]
        validated = timestamp(candidate["validated_at"]) if candidate.get("validated_at") else None
        listing = "unverified"
        if candidate["security_status"] == "inactive":
            listing = "recorded_inactive"
        elif candidate["security_status"] == "active" and validated and candidate.get("validation_source"):
            if validated > end:
                listing = "validation_after_report_cutoff"
            elif end - validated > timedelta(days=listing_max_age_days):
                listing = "review_due"
            elif not candidate.get("issuer") or not candidate.get("venue"):
                listing = "incomplete_metadata"
            else:
                listing = "recorded_active"
        records = [r for r in state["coverage"] if r["ticker"] == ticker]
        scopes = {(r["source"], r["query_scope"]) for r in records}
        scopes |= {(r["source"], r["query_scope"]) for r in state["posts"] if r["resolved_ticker"] == ticker}
        for source, scope in sorted(scopes) or [(None, None)]:
            evaluation = features(state, ticker, source, end, window, scope, end) if source else None
            known = [r for r in records if r["source"] == source and r["query_scope"] == scope
                     and timestamp(r["collected_at"]) <= end]
            last_end = max((r["end"] for r in known), default=None)
            actions = []
            if listing != "recorded_active":
                actions.append("Review listing, issuer, venue, and dated source evidence")
            if not evaluation or evaluation["coverage_status"] != "complete":
                actions.append("Collect or restore the full source query for this window")
            if not evaluation or evaluation["baseline_status"] != "available":
                actions.append("Build four complete prior comparison windows with a nonzero baseline")
            if evaluation and evaluation["label"] == "Insufficient author data":
                actions.append("Check permitted author identifiers in the export")
            if not actions:
                actions.append("Record an evaluation and inspect its source evidence")
            rows.append({"ticker": ticker, "listing_review": listing, "source": source,
                         "query_scope": scope, "window": window, "window_end": end.isoformat(),
                         "last_collected_window_end": last_end,
                         "coverage_status": evaluation["coverage_status"] if evaluation else "not_collected",
                         "baseline_status": evaluation["baseline_status"] if evaluation else "insufficient_baseline",
                         "baseline_windows": evaluation["baseline_windows"] if evaluation else 0,
                         "feature_status": evaluation["label"] if evaluation else "Insufficient coverage",
                         "next_actions": actions})
    return {"generated_at": now(), "as_of": end.isoformat(), "data_kind": state["data_kind"],
            "listing_review_interval_days": listing_max_age_days,
            "analysis_mode": "retrospective_import", "rows": rows,
            "research_candidates": len({r["ticker"] for r in rows}),
            "candidates_needing_listing_review": len({r["ticker"] for r in rows if r["listing_review"] != "recorded_active"})}


def research_readiness(workspace=DEFAULT_WORKSPACE, as_of=None, window="24h"):
    return readiness(read_state(workspace), as_of, window)


def attention_queue(state, as_of=None, include_reviewed=False):
    end = timestamp(as_of or now())
    candidates = {r["ticker"] for r in state["universe"] if r["membership"] == "research"}
    latest = {}
    for row in state["evaluations"]:
        if row["ticker"] not in candidates or timestamp(row["generated_at"]) > end:
            continue
        key = tuple(row[k] for k in ("ticker", "source", "query_scope", "window", "score_version"))
        ordering = (timestamp(row["end"]), timestamp(row["generated_at"]), row["id"])
        if key not in latest or ordering > latest[key][0]:
            latest[key] = (ordering, row)
    reviews = {r["evaluation_id"]: r for r in state.get("social_reviews", []) if timestamp(r["reviewed_at"]) <= end}
    result = []
    for _, row in latest.values():
        if row["label"] != "Elevated attention":
            continue
        review = reviews.get(row["id"])
        if review and not include_reviewed:
            continue
        stale = end - timestamp(row["end"]) > timedelta(hours=WINDOWS[row["window"]])
        baseline_start = timestamp(row["end"]) - timedelta(hours=5 * WINDOWS[row["window"]])
        updated = any(r["source"] == row["source"] and r["query_scope"] == row["query_scope"]
                      and r["resolved_ticker"] == row["ticker"]
                      and timestamp(row["generated_at"]) < timestamp(r["imported_at"]) <= end
                      and baseline_start <= timestamp(r["published_at"]) < timestamp(row["end"])
                      for r in state["posts"])
        updated |= any(r["source"] == row["source"] and r["query_scope"] == row["query_scope"]
                       and r["ticker"] == row["ticker"]
                       and timestamp(row["generated_at"]) < timestamp(r["imported_at"]) <= end
                       and timestamp(r["start"]) < timestamp(row["end"]) and timestamp(r["end"]) > baseline_start
                       for r in state["coverage"])
        result.append({k: row[k] for k in ("id", "ticker", "source", "query_scope", "window", "end",
                                           "generated_at", "score_version", "social_attention_score", "analysis_mode", "data_kind")} |
                      {"age_status": "historical_window" if stale else "recent_window",
                       "new_evidence_since_evaluation": updated,
                       "review_status": "reviewed" if review else "needs_review",
                       "review_note": review["note"] if review else None})
    return sorted(result, key=lambda r: (timestamp(r["end"]), r["social_attention_score"]), reverse=True)


def review_evaluation(workspace, evaluation_id, note):
    note = required(note, "review note", 2000)
    with writer_lock(workspace):
        state = read_state(workspace)
        if evaluation_id not in {r["id"] for r in state["evaluations"]}:
            raise ValueError("Unknown evaluation; refresh the queue")
        result = {"evaluation_id": evaluation_id, "note": note, "reviewed_at": now()}
        state.setdefault("social_reviews", []).append(result)
        save_json(Path(workspace) / "social.json", state)
    return result


def combined_classification(market_status, social_evaluation):
    """Join evidence labels while preserving the independent component scores."""
    market = market_status == "alert"
    if social_evaluation is None or social_evaluation.get("coverage_status") != "complete":
        return "Insufficient coverage"
    social = social_evaluation.get("label") == "Elevated attention"
    if market and social:
        return "Combined concern"
    if market:
        return "Market anomaly"
    if social:
        return "Elevated social attention"
    return "Normal"
