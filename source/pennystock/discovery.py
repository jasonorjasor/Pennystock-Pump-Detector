"""Versioned, review-first discovery and candidate registry."""
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from .calendar import completed_session, sessions_between
from .core import normalize_bars, valid_bars
from .pipeline import fetch_bars, load_watchlist, validate_ticker
from .storage import DEFAULT_WORKSPACE, ROOT, atomic_text, save_json, writer_lock

DISCOVERY_VERSION = "discovery-v1"
DIRECTORIES = {
    "nasdaq": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "other": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
}
STATES = {"discovered", "needs_review", "approved", "rejected", "expired", "held", "archived"}
ACTIVE_LIMIT = 50
CATALYST_CATEGORIES = {"none_found", "company_news", "sec_filing", "analyst_or_media", "unknown"}
CORPORATE_ACTION_STATUSES = {"none_found", "split", "offering", "symbol_change", "other", "unknown"}
DATA_QUALITY_STATUSES = {"complete", "partial", "failed", "unknown"}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def _empty():
    return {"schema_version": 1, "identities": [], "candidates": [], "transitions": [],
            "discovery_runs": [], "observations": [], "universe_snapshots": [], "revalidation_runs": []}


def read_registry(workspace=DEFAULT_WORKSPACE):
    path = Path(workspace) / "candidates.json"
    if not path.exists():
        return _empty()
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != 1:
        raise ValueError("Unsupported candidate registry schema")
    for key in _empty():
        state.setdefault(key, _empty()[key])
    return state


def _transition(state, ticker, new_state, reason, reviewer, stamp=None, snapshot=None, quiet=False, review=None):
    if new_state not in STATES:
        raise ValueError(f"Invalid candidate state: {new_state}")
    validate_ticker(ticker)
    stamp = stamp or utcnow()
    previous = next((r for r in state["candidates"] if r["ticker"] == ticker), None)
    old_state = previous["state"] if previous else None
    if new_state == "approved":
        active = sum(r["state"] == "approved" and r["ticker"] != ticker for r in state["candidates"])
        if active >= ACTIVE_LIMIT:
            raise ValueError("Active universe capacity is 50; hold or archive a candidate first")
    row = {"ticker": ticker, "state": new_state, "updated_at": stamp,
           "reason": reason.strip(), "reviewer": reviewer.strip(),
           "first_seen_at": previous["first_seen_at"] if previous else stamp,
           "quiet_comparison": quiet if new_state == "needs_review" else previous.get("quiet_comparison", False) if previous else False}
    if not row["reason"] or not row["reviewer"]:
        raise ValueError("Reason and reviewer are required")
    if review and len(row["reason"]) < 20:
        raise ValueError("Structured review reason must be at least 20 characters and explain the decision")
    state["candidates"] = [r for r in state["candidates"] if r["ticker"] != ticker] + [row]
    state["transitions"].append({"ticker": ticker, "prior_state": old_state,
        "new_state": new_state, "timestamp": stamp, "reason": row["reason"],
        "reviewer": row["reviewer"], "source_snapshot": snapshot, "review": review})
    return row


def initialize_registry(workspace=DEFAULT_WORKSPACE, watchlist=ROOT / "source/MAIN/watchlist.txt"):
    """Seed the approved cohort once from the local reviewed watchlist."""
    with writer_lock(workspace):
        state = read_registry(workspace)
        if state["candidates"]:
            return {"state": "already_initialized", "approved": len(approved_tickers(state))}
        for ticker in load_watchlist(watchlist):
            _transition(state, ticker, "approved", "Reviewed starting cohort", "project-owner")
        save_json(Path(workspace) / "candidates.json", state)
        _write_approved(Path(workspace), state)
    return {"state": "initialized", "approved": len(approved_tickers(state))}


def approved_tickers(state):
    return sorted(r["ticker"] for r in state["candidates"] if r["state"] == "approved")


def _write_approved(workspace, state):
    tickers = approved_tickers(state)
    atomic_text(Path(workspace) / "approved_watchlist.txt", "".join(f"{x}\n" for x in tickers))
    return tickers


def validate_review(review):
    """Validate a structured human review without interpreting it as proof of misconduct."""
    required = {"identity_checked", "liquidity_checked", "catalyst_category",
                "corporate_action", "data_quality"}
    if not review or not required.issubset(review):
        raise ValueError("Structured review is required: identity, liquidity, catalyst, corporate action, and data quality")
    if review["identity_checked"] is not True or review["liquidity_checked"] is not True:
        raise ValueError("Identity and liquidity must be checked before a decision")
    if review["catalyst_category"] not in CATALYST_CATEGORIES:
        raise ValueError("Invalid catalyst category")
    if review["corporate_action"] not in CORPORATE_ACTION_STATUSES:
        raise ValueError("Invalid corporate-action status")
    if review["data_quality"] not in DATA_QUALITY_STATUSES:
        raise ValueError("Invalid data-quality status")
    url = (review.get("evidence_url") or "").strip()
    if url and not url.startswith(("https://", "http://")):
        raise ValueError("Evidence URL must use http or https")
    return {**review, "evidence_url": url}


def change_candidate(workspace, ticker, new_state, reason, reviewer="project-owner", review=None):
    ticker = ticker.upper()
    with writer_lock(workspace):
        state = read_registry(workspace)
        if not any(r["ticker"] == ticker for r in state["candidates"]):
            raise ValueError("Unknown candidate; run discover first")
        review = validate_review(review) if new_state in {"approved", "rejected"} else review
        row = _transition(state, ticker, new_state, reason, reviewer, review=review)
        save_json(Path(workspace) / "candidates.json", state)
        _write_approved(workspace, state)
    return row


def list_candidates(workspace=DEFAULT_WORKSPACE, state_filter=None):
    state = read_registry(workspace)
    rows = state["candidates"]
    if state_filter:
        rows = [r for r in rows if r["state"] == state_filter]
    latest = {}
    for row in state["observations"]:
        if row["ticker"] not in latest or row["as_of"] > latest[row["ticker"]]["as_of"]:
            latest[row["ticker"]] = row
    reviews = {}
    for transition in state["transitions"]:
        if transition.get("review"):
            reviews[transition["ticker"]] = transition["review"] | {"reviewed_at": transition["timestamp"]}
    return [r | {"latest_observation": latest.get(r["ticker"]), "latest_review": reviews.get(r["ticker"])}
            for r in sorted(rows, key=lambda x: x["ticker"])]


def parse_directory(text, source, retrieved_at=None):
    """Parse official Nasdaq Trader pipe directories and exclude non-equity products."""
    retrieved_at = retrieved_at or utcnow()
    frame = pd.read_csv(io.StringIO(text), sep="|")
    frame = frame[~frame.iloc[:, 0].astype(str).str.startswith("File Creation Time")]
    rows = []
    for raw in frame.to_dict("records"):
        symbol = str(raw.get("Symbol") or raw.get("ACT Symbol") or "").strip().upper()
        name = str(raw.get("Security Name") or "").strip()
        if not symbol or not re.fullmatch(r"[A-Z0-9.-]{1,20}", symbol):
            continue
        etf = str(raw.get("ETF", "N")).upper() == "Y"
        test = str(raw.get("Test Issue", "N")).upper() == "Y"
        lowered = name.lower()
        excluded = etf or test or any(token in lowered for token in
            [" warrant", " warrants", " right", " rights", " unit", " units",
             "preferred", " preference", " fund", " etf", " note due"])
        if excluded:
            continue
        venue = str(raw.get("Exchange") or "NASDAQ").strip()
        rows.append({"symbol": symbol, "issuer": name, "venue": venue,
                     "security_type": "ADR/ADS" if re.search(r"\b(ADR|ADS|depositary shar)", name, re.I) else "common_share",
                     "directory_status": "active", "listing_deficiency": str(raw.get("Financial Status", "N")) not in {"N", "nan", ""},
                     "source": source, "retrieved_at": retrieved_at})
    return rows


def fetch_directories(symbols_dir=None):
    rows = []
    for name, url in DIRECTORIES.items():
        if symbols_dir:
            text = (Path(symbols_dir) / f"{name}.txt").read_text(encoding="utf-8-sig")
            source = str(Path(symbols_dir) / f"{name}.txt")
        else:
            request = Request(url, headers={"User-Agent": "Microcap-Observatory/1.0 research"})
            with urlopen(request, timeout=30) as response:
                text, source = response.read().decode("utf-8-sig"), url
        rows.extend(parse_directory(text, source))
    unique = {}
    for row in rows:
        unique.setdefault(row["symbol"], row)
    return list(unique.values())


def discovery_features(bars, day):
    bars = normalize_bars(bars).loc[:day]
    if day not in bars.index:
        return {"collection_status": "stale"}
    mask = valid_bars(bars)
    clean = bars.where(mask).dropna(subset=["Close", "Volume"])
    if len(clean) < 21 or clean.index[-1] != day:
        return {"collection_status": "insufficient_history", "valid_sessions": len(clean)}
    current, prior = clean.iloc[-1], clean.iloc[-21:-1]
    dollar = prior.Close * prior.Volume
    mean, std = prior.Volume.mean(), prior.Volume.std()
    returns = clean.Close.pct_change(fill_method=None)
    features = {"collection_status": "complete", "latest_price": float(current.Close),
        "median_dollar_volume_20d": float(dollar.median()), "volume_ratio": float(current.Volume / (mean + 1e-9)),
        "volume_z": float((current.Volume - mean) / (std + 1e-9)), "return_1d": float(returns.iloc[-1]),
        "return_5d": float(current.Close / clean.Close.iloc[-6] - 1) if len(clean) >= 6 else None,
        "return_20d": float(current.Close / clean.Close.iloc[-21] - 1),
        "gap": float(current.Open / clean.Close.iloc[-2] - 1),
        "volatility": float((current.High - current.Low) / current.Close), "valid_sessions": int(len(clean)),
        "quiet_baseline": bool(prior.Volume.iloc[-10:].median() <= prior.Volume.median() * 1.25)}
    score = 0
    score += 30 if features["volume_z"] >= 3 else 20 if features["volume_z"] >= 2 else 0
    score += 25 if features["volume_ratio"] >= 5 else 15 if features["volume_ratio"] >= 3 else 0
    score += 25 if features["return_1d"] >= .20 else 15 if features["return_1d"] >= .10 else 0
    score += 10 if features["median_dollar_volume_20d"] >= 250000 else 0
    score += 5 if features["quiet_baseline"] else 0
    score += 5 if features["valid_sessions"] >= 40 else 0
    features["discovery_score"] = score
    return features


def _live_batches(identities, start, end, chunk_size=50):
    """Download in bounded batches; a failed batch remains failed instead of becoming zero activity."""
    import yfinance as yf
    cache = ROOT / "runs" / ".yfinance_cache"
    cache.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache))
    result, errors = {}, {}
    symbol_map = {r["symbol"]: r["symbol"].replace(".", "-") for r in identities}
    symbols = list(symbol_map)
    for offset in range(0, len(symbols), chunk_size):
        chunk = symbols[offset:offset + chunk_size]
        provider_chunk = [symbol_map[t] for t in chunk]
        try:
            raw = None
            last_error = None
            for attempt in range(3):
                try:
                    raw = yf.download(provider_chunk, start=str(start.date()), end=str(end.date()), auto_adjust=True,
                                      actions=True, progress=False, timeout=45, threads=False, group_by="column")
                    if raw is not None and not raw.empty:
                        break
                    last_error = ValueError("provider returned no price rows")
                except Exception as exc:
                    last_error = exc
                if attempt < 2:
                    time.sleep(2 ** attempt)
            if raw is None or raw.empty:
                raise RuntimeError(f"batch unavailable after 3 attempts: {last_error}")
            for ticker in chunk:
                try:
                    result[ticker] = normalize_bars(raw, symbol_map[ticker])
                except Exception as exc:
                    errors[ticker] = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            for ticker in chunk:
                errors[ticker] = f"{type(exc).__name__}: {exc}"
    return result, errors


def discover(workspace=DEFAULT_WORKSPACE, session=None, max_price=5.0, symbols_dir=None,
             prices_dir=None, max_new=10, force=False):
    day = completed_session(session)
    run_id = f"{day.date()}_{DISCOVERY_VERSION}"
    prior_state = read_registry(workspace)
    prior_run = next((r for r in prior_state["discovery_runs"] if r["id"] == run_id), None)
    if prior_run and not force:
        nominated = [r["ticker"] for r in prior_state["transitions"]
                     if r.get("source_snapshot") == run_id and r["new_state"] == "needs_review"]
        return prior_run | {"nominated_candidates": nominated, "cached": True}
    identities = fetch_directories(symbols_dir)
    observations, evaluated = [], []
    start, end = day - pd.Timedelta(days=120), day + pd.Timedelta(days=1)
    live_bars, live_errors = ({}, {}) if prices_dir else _live_batches(identities, start, end)
    for identity in identities:
        ticker = identity["symbol"]
        try:
            if prices_dir:
                bars = fetch_bars(ticker, start, end, prices_dir)
            elif ticker in live_errors:
                raise ValueError(live_errors[ticker])
            else:
                bars = live_bars[ticker]
            feature = discovery_features(bars.reindex(sessions_between(day - pd.Timedelta(days=120), day)), day)
        except Exception as exc:
            feature = {"collection_status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        record = {"ticker": ticker, "as_of": str(day.date()), "observed_at": utcnow(),
            "score_version": DISCOVERY_VERSION, "source": identity["source"], "synthetic": bool(prices_dir),
            "coverage_status": "complete" if feature.get("collection_status") == "complete" else feature.get("collection_status"),
            "listing_deficiency": identity["listing_deficiency"], "split_or_transition": "unknown"} | feature
        evaluated.append(record)
        if feature.get("collection_status") == "complete" and feature["latest_price"] <= max_price:
            observations.append(record)
    observations.sort(key=lambda r: (-r["discovery_score"], -r["median_dollar_volume_20d"], r["ticker"]))
    with writer_lock(workspace):
        state = read_registry(workspace)
        state["identities"].extend(i for i in identities if not any(
            old["symbol"] == i["symbol"] and old["retrieved_at"] == i["retrieved_at"] for old in state["identities"]))
        existing = {r["ticker"]: r for r in state["candidates"]}
        # Ten completed sessions is a review policy; history is retained.
        for candidate in list(state["candidates"]):
            if candidate["state"] == "needs_review":
                first_seen = pd.Timestamp(candidate["first_seen_at"]).tz_localize(None).normalize()
                elapsed = sessions_between(first_seen, day) if first_seen <= day else []
                if len(elapsed) > 10:
                    _transition(state, candidate["ticker"], "expired", "Unreviewed for 10 completed sessions", "system")
        existing = {r["ticker"]: r for r in state["candidates"]}
        nominated = 0
        nominated_symbols = []
        unseen = [r for r in observations if r["ticker"] not in existing]
        quiet_count = min(len(unseen) // 5, max(1, round(max_new * .2))) if unseen else 0
        signal_count = max_new - quiet_count
        selected = unseen[:signal_count]
        quiet_pool = [r for r in reversed(unseen[signal_count:]) if r["median_dollar_volume_20d"] >= 250000]
        selected += quiet_pool[:quiet_count]
        quiet_symbols = {r["ticker"] for r in quiet_pool[:quiet_count]}
        for row in selected:
            if nominated < max_new:
                _transition(state, row["ticker"], "needs_review", "Ranked by discovery-v1", "system",
                            snapshot=run_id, quiet=row["ticker"] in quiet_symbols)
                nominated += 1
                nominated_symbols.append(row["ticker"])
        keys = {(r["ticker"], r["as_of"], r["score_version"]) for r in state["observations"]}
        state["observations"].extend(r for r in evaluated if (r["ticker"], r["as_of"], r["score_version"]) not in keys)
        run = {"id": run_id, "session": str(day.date()), "retrieved_at": utcnow(), "score_version": DISCOVERY_VERSION,
               "max_price": max_price, "eligible": len(observations), "nominated": nominated,
               "evaluated": len(evaluated), "failed_or_incomplete": sum(r["coverage_status"] != "complete" for r in evaluated),
               "status": "partial" if any(r["coverage_status"] != "complete" for r in evaluated) else "complete",
               "synthetic": bool(prices_dir)}
        if not any(r["id"] == run_id for r in state["discovery_runs"]):
            state["discovery_runs"].append(run)
        save_json(Path(workspace) / "candidates.json", state)
        _write_approved(workspace, state)
    return run | {"nominated_candidates": nominated_symbols,
                  "ranked_top": [r["ticker"] for r in observations[:max_new]], "cached": False}


def capture_universe(workspace, session):
    with writer_lock(workspace):
        state = read_registry(workspace)
        tickers = approved_tickers(state)
        snapshot = {"session": str(pd.Timestamp(session).date()), "captured_at": utcnow(), "tickers": tickers}
        prior = next((r for r in state["universe_snapshots"] if r["session"] == snapshot["session"]), None)
        if prior:
            return prior
        state["universe_snapshots"].append(snapshot)
        save_json(Path(workspace) / "candidates.json", state)
        _write_approved(workspace, state)
        return snapshot


def revalidate(workspace=DEFAULT_WORKSPACE, as_of=None):
    """Record a weekly identity/data review without silently changing membership."""
    day = completed_session(as_of)
    with writer_lock(workspace):
        state = read_registry(workspace)
        rows = []
        for ticker in approved_tickers(state):
            identities = [r for r in state["identities"] if r["symbol"] == ticker]
            observations = [r for r in state["observations"] if r["ticker"] == ticker]
            identity = max(identities, key=lambda r: r["retrieved_at"], default=None)
            observation = max(observations, key=lambda r: r["as_of"], default=None)
            issues = []
            if not identity or identity.get("directory_status") != "active":
                issues.append("listing_identity_unverified")
            if identity and identity.get("listing_deficiency"):
                issues.append("listing_deficiency_reported")
            if not observation or observation.get("coverage_status") != "complete":
                issues.append("recent_price_unavailable")
            if observation and observation.get("split_or_transition") == "unknown":
                issues.append("corporate_action_review_needed")
            rows.append({"ticker": ticker, "status": "review_needed" if issues else "current", "issues": issues})
        report = {"as_of": str(day.date()), "recorded_at": utcnow(), "rows": rows,
                  "review_needed": sum(r["status"] == "review_needed" for r in rows)}
        state["revalidation_runs"].append(report)
        save_json(Path(workspace) / "candidates.json", state)
    return report


def nominate_from_social(workspace, evaluation_id, reviewer="system"):
    """Turn sufficient elevated social evidence into review, never approval."""
    from .social import read_state
    social = read_state(workspace)
    evaluation = next((r for r in social["evaluations"] if r["id"] == evaluation_id), None)
    if not evaluation:
        raise ValueError("Unknown social evaluation")
    if evaluation.get("coverage_status") != "complete" or evaluation.get("label") != "Elevated attention":
        raise ValueError("Social nomination requires complete, elevated evidence")
    if evaluation.get("unique_authors_observed", 0) < 2:
        raise ValueError("Social nomination requires multiple observed authors")
    ticker = evaluation["ticker"]
    with writer_lock(workspace):
        state = read_registry(workspace)
        if not any(r["symbol"] == ticker for r in state["identities"]):
            raise ValueError("Ticker must resolve to a validated directory identity")
        current = next((r for r in state["candidates"] if r["ticker"] == ticker), None)
        if current and current["state"] == "approved":
            return current
        row = _transition(state, ticker, "needs_review", "Elevated social attention with complete coverage",
                          reviewer, snapshot=evaluation_id)
        save_json(Path(workspace) / "candidates.json", state)
        _write_approved(workspace, state)
    return row
