"""Local social evidence research. Imports are retrospective, never live warnings."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
from statistics import mean
from urllib.parse import urlsplit

from .pipeline import load_watchlist, validate_ticker
from . import SCORE_VERSION as MARKET_SCORE_VERSION
from .storage import DEFAULT_WORKSPACE, ROOT, save_json, writer_lock

WINDOWS = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}
SCORE_VERSION = "social-attention-experimental-v1"
RULES = {"mention_growth": (3, 30), "author_growth": (2, 20),
         "author_concentration": (.5, 10), "repeated_text": (.5, 15),
         "shared_link": (.5, 10), "minute_concentration": (.5, 15)}
AMBIGUOUS = {"A", "I", "AI", "IT", "ON", "CAN", "ALL", "FOR", "ARE", "AT", "BY", "BE", "SO"}


def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO 8601 string with timezone")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"Invalid timestamp: {value}") from None
    if result.tzinfo is None:
        raise ValueError("Timestamps must include a timezone")
    return result.astimezone(timezone.utc)


def required(value, name, limit=1000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be nonempty text, at most {limit} characters")
    return value.strip()


def symbol(value):
    value = required(value, "ticker", 20).upper()
    validate_ticker(value)
    return value


def read_state(workspace):
    path = Path(workspace) / "social.json"
    if not path.exists():
        return {"schema_version": 1, "data_kind": None, "universe": [],
                "universe_history": [], "posts": [], "coverage": [], "evaluations": []}
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != 1:
        raise ValueError("Unsupported social store schema version")
    return state


def universe_update(workspace, ticker, reason, membership="research", issuer=None,
                    venue=None, security_status="unverified", validation_source=None,
                    data_availability="unknown", notes=None):
    """Append a version; membership is independent of whether a security is active."""
    ticker, reason = symbol(ticker), required(reason, "reason")
    if membership not in {"research", "archived"}:
        raise ValueError("membership must be research or archived")
    if security_status not in {"unverified", "active", "inactive"}:
        raise ValueError("Invalid security_status")
    if security_status != "unverified" and not validation_source:
        raise ValueError("Verified security status requires a validation source")
    for name, value in {"issuer": issuer, "venue": venue, "validation_source": validation_source,
                        "data_availability": data_availability, "notes": notes}.items():
        if value is not None:
            required(value, name)
    with writer_lock(workspace):
        state = read_state(workspace)
        previous = next((r for r in state["universe"] if r["ticker"] == ticker), None)
        stamp = now()
        row = {"ticker": ticker, "issuer": issuer, "venue": venue,
               "membership": membership, "security_status": security_status,
               "added_at": previous["added_at"] if previous else stamp,
               "removed_at": (previous.get("removed_at") or stamp) if membership == "archived" and previous else stamp if membership == "archived" else None,
               "reason": reason, "updated_at": stamp,
               "validated_at": stamp if security_status != "unverified" else None,
               "validation_source": validation_source, "data_availability": data_availability,
               "notes": notes, "version": previous["version"] + 1 if previous else 1}
        state["universe"] = [r for r in state["universe"] if r["ticker"] != ticker] + [row]
        state["universe_history"].append(row.copy())
        save_json(Path(workspace) / "social.json", state)
    return row


def universe_init(workspace=DEFAULT_WORKSPACE, watchlist=ROOT / "source/MAIN/watchlist.txt"):
    path = Path(watchlist)
    if not path.exists():
        raise ValueError("Watchlist does not exist; supply --watchlist")
    tickers = load_watchlist(path)
    for ticker in tickers:
        symbol(ticker)
    # Initialization is atomic, including the original dated snapshot.
    with writer_lock(workspace):
        state = read_state(workspace)
        if state.get("watchlist_snapshot"):
            return {"state": "already_initialized", "count": len(state["universe"])}
        stamp = now()
        state["watchlist_snapshot"] = {"captured_at": stamp, "tickers": tickers,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "reason": "Existing watchlist preserved; current listings have not been validated"}
        existing = {r["ticker"] for r in state["universe"]}
        for ticker in tickers:
            if ticker in existing:
                continue
            row = {"ticker": ticker, "issuer": None, "venue": None,
                   "membership": "research", "security_status": "unverified",
                   "added_at": stamp, "removed_at": None, "updated_at": stamp,
                   "reason": "Imported historical watchlist; requires revalidation",
                   "validated_at": None, "validation_source": None,
                   "data_availability": "unknown", "notes": None, "version": 1}
            state["universe"].append(row)
            state["universe_history"].append(row.copy())
        save_json(Path(workspace) / "social.json", state)
    return {"state": "initialized", "count": len(state["universe"])}


def resolve(text, universe):
    """Conservative single-ticker resolution. Multiple symbols stay unresolved."""
    candidates = []
    for row in universe:
        ticker = row["ticker"]
        token = re.escape(ticker)
        if re.search(r"\$" + token + r"(?![A-Za-z0-9.])", text, re.I):
            candidates.append((ticker, 1.0, "cashtag"))
        elif re.search(r"(?<![\w$])" + token + r"(?![\w.])", text):
            issuer = row.get("issuer")
            if issuer and issuer.casefold() in text.casefold():
                candidates.append((ticker, .9, "ticker_and_issuer"))
            elif ticker not in AMBIGUOUS and len(ticker) >= 4:
                candidates.append((ticker, .8, "uppercase_ticker"))
    if len(candidates) == 1:
        return candidates[0]
    return None, 0.0, "multiple_candidates" if candidates else "unresolved"


def normalize_post(raw, state, stamp):
    if not isinstance(raw, dict):
        raise ValueError("Each observation must be an object")
    source = required(raw.get("source"), "source", 100)
    scope = required(raw.get("query_scope"), "query_scope", 1000)
    post_id = required(raw.get("source_post_id"), "source_post_id", 300)
    published, collected = timestamp(raw.get("published_at")), timestamp(raw.get("collected_at"))
    if published > collected or collected > timestamp(stamp):
        raise ValueError("Require published_at <= collected_at <= import time")
    text = required(raw.get("text"), "text", 20000)
    raw_ticker = raw.get("raw_ticker_text", "")
    if not isinstance(raw_ticker, str) or len(raw_ticker) > 1000:
        raise ValueError("raw_ticker_text must be text of at most 1000 characters")
    url = required(raw.get("url"), "url", 2000)
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Evidence URL must be an http(s) URL without credentials")
    author = raw.get("author_id")
    if author is not None:
        required(author, "author_id", 500)
    ticker, confidence, method = resolve(text, state["universe"])
    engagement = raw.get("engagement", {})
    if not isinstance(engagement, dict) or any(
        not isinstance(k, str) or type(v) is not int or v < 0 for k, v in engagement.items()
    ):
        raise ValueError("Engagement must contain nonnegative integer counts")
    language = raw.get("language")
    if language is not None:
        required(language, "language", 30)
    return {"id": hashlib.sha256(json.dumps([source, post_id, scope]).encode()).hexdigest(),
            "source": source, "query_scope": scope, "source_post_id": post_id, "url": url,
            "published_at": published.isoformat(), "collected_at": collected.isoformat(),
            "imported_at": stamp, "raw_ticker_text": raw_ticker, "resolved_ticker": ticker,
            "resolution_confidence": confidence, "resolution_method": method,
            "author_hash": hashlib.sha256((state["author_salt"] + source + "\0" + author).encode()).hexdigest() if author else None,
            "text": text, "engagement": engagement, "language": language,
            "collection_status": "collected"}


def normalize_coverage(raw, state, stamp):
    if not isinstance(raw, dict):
        raise ValueError("Each coverage record must be an object")
    source, ticker = required(raw.get("source"), "source", 100), symbol(raw.get("ticker"))
    if ticker not in {r["ticker"] for r in state["universe"]}:
        raise ValueError(f"Unknown universe ticker: {ticker}")
    start, end, collected = [timestamp(raw.get(k)) for k in ("start", "end", "collected_at")]
    if not start < end <= collected <= timestamp(stamp):
        raise ValueError("Coverage requires start < end <= collected_at <= import time")
    status = raw.get("status")
    if not isinstance(status, str) or status not in {"complete", "not_collected", "unavailable", "failed"}:
        raise ValueError("Invalid coverage status")
    scope = required(raw.get("query_scope"), "query_scope", 1000)
    error = raw.get("error")
    if error is not None:
        required(error, "error")
    row = {"source": source, "ticker": ticker, "start": start.isoformat(), "end": end.isoformat(),
           "collected_at": collected.isoformat(), "status": status, "query_scope": scope, "error": error}
    row["id"] = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
    row["imported_at"] = stamp
    return row


def prepare_import(state, payload, meta):
    """Validate and stage in memory. Shared by read-only preview and locked commit."""
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise ValueError("Import requires schema_version 1")
    kind = payload.get("data_kind")
    if not isinstance(kind, str) or kind not in {"research", "synthetic"}:
        raise ValueError("data_kind must be research or synthetic")
    for key in ("observations", "coverage"):
        if not isinstance(payload.get(key), list) or len(payload[key]) > 10000:
            raise ValueError(f"{key} must be a list of at most 10000 records")
    if kind == "synthetic" and meta and not meta.get("social_synthetic"):
        raise ValueError("Synthetic imports require a separate social demo workspace")
    if kind == "research" and (meta.get("social_synthetic") or meta.get("kind") == "offline-demo"):
        raise ValueError("Research imports require a workspace separate from demonstrations")
    if state["data_kind"] not in {None, kind}:
        raise ValueError("Research and synthetic imports cannot share a social store")
    state = deepcopy(state)
    state["data_kind"] = kind
    state.setdefault("author_salt", secrets.token_hex(32))
    stamp = now()
    posts = [normalize_post(raw, state, stamp) for raw in payload["observations"]]
    coverage = [normalize_coverage(raw, state, stamp) for raw in payload["coverage"]]
    added = {}
    for key, incoming in (("posts", posts), ("coverage", coverage)):
        indexed = {r["id"]: r for r in state[key]}
        before = len(indexed)
        for row in incoming:
            old = indexed.get(row["id"])
            if old:
                ignored = {"imported_at", "collected_at", "engagement", "resolved_ticker",
                           "resolution_confidence", "resolution_method"} if key == "posts" else {"imported_at"}
                if {k: v for k, v in old.items() if k not in ignored} != {k: v for k, v in row.items() if k not in ignored}:
                    raise ValueError("Conflicting duplicate ID; original evidence was preserved")
            else:
                indexed[row["id"]] = row
        state[key] = list(indexed.values())
        added[key] = len(indexed) - before
    summary = {"added": added, "data_kind": kind,
               "unresolved_total": sum(r["resolved_ticker"] is None for r in state["posts"]),
               "sources": sorted({r["source"] for r in posts + coverage}),
               "resolved_tickers": sorted({r["resolved_ticker"] for r in posts if r["resolved_ticker"]})}
    return state, summary


def import_metadata(workspace, payload=None):
    if (Path(workspace) / "data").exists():
        raise ValueError("Choose a new workspace, not an existing legacy run")
    if isinstance(payload, dict) and payload.get("data_kind") == "synthetic" and Path(workspace).resolve() == DEFAULT_WORKSPACE.resolve():
        raise ValueError("Synthetic imports cannot use the default research workspace; choose a separate demo workspace")
    path = Path(workspace) / "workspace.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def preview_import(workspace, payload):
    return prepare_import(read_state(workspace), payload, import_metadata(workspace, payload))[1]


def import_payload(workspace, payload):
    """Revalidate against current state under the writer lock, even after a preview."""
    with writer_lock(workspace):
        meta = import_metadata(workspace, payload)
        state, result = prepare_import(read_state(workspace), payload, meta)
        save_json(Path(workspace) / "social.json", state)
        if not meta:
            save_json(Path(workspace) / "workspace.json", {"kind": "social-research", "social_synthetic": state["data_kind"] == "synthetic",
                      "score_version": MARKET_SCORE_VERSION if state["data_kind"] == "research" else "synthetic-social-only"})
    return result


def parse_import(content):
    if len(content) > 10_000_000:
        raise ValueError("Import exceeds 10 MB; split it into smaller batches")
    def reject_constant(value):
        raise ValueError(f"Non-finite JSON number: {value}")
    try:
        return json.loads(content.decode("utf-8-sig"), parse_constant=reject_constant)
    except UnicodeDecodeError:
        raise ValueError("Import must be UTF-8 JSON") from None


def social_import(source, workspace=DEFAULT_WORKSPACE, profile=None):
    path = Path(source)
    if path.stat().st_size > 10_000_000:
        raise ValueError("Import exceeds 10 MB; split it into smaller batches")
    payload = parse_import(path.read_bytes())
    if profile not in {None, "subreddit-export"}:
        raise ValueError("Unknown social import profile")
    if profile == "subreddit-export":
        for row in payload.get("observations", []):
            host = (urlsplit(str(row.get("url", ""))).hostname or "").lower()
            if host != "reddit.com" and not host.endswith(".reddit.com"):
                raise ValueError("Subreddit exports require reddit.com source URLs")
            if not str(row.get("source", "")).startswith("reddit:"):
                raise ValueError("Use a source label such as reddit:pennystocks")
    return import_payload(workspace, payload)


def coverage_status(state, ticker, source, start, end, known_at, query_scope):
    records = [r for r in state["coverage"] if r["ticker"] == ticker and r["source"] == source
               and r["query_scope"] == query_scope and timestamp(r["collected_at"]) <= known_at
               and timestamp(r["start"]) < end and timestamp(r["end"]) > start]
    edges = sorted({start, end} | {max(start, timestamp(r["start"])) for r in records}
                   | {min(end, timestamp(r["end"])) for r in records})
    statuses = []
    for left, right in zip(edges, edges[1:]):
        covering = [r for r in records if timestamp(r["start"]) <= left and timestamp(r["end"]) >= right]
        # Successful recovery establishes coverage; failed retries do not erase it.
        statuses.append("complete" if any(r["status"] == "complete" for r in covering) else
                        max(covering, key=lambda r: r["collected_at"])["status"] if covering else "not_collected")
    if all(s == "complete" for s in statuses):
        return "complete"
    return next((s for s in ("failed", "unavailable", "not_collected") if s in statuses), "not_collected")


def features(state, ticker, source, end, window="24h", query_scope=None, known_at=None):
    ticker, source = symbol(ticker), required(source, "source", 100)
    if ticker not in {r["ticker"] for r in state["universe"]}:
        raise ValueError("Ticker is not in the research universe")
    if window not in WINDOWS:
        raise ValueError("window must be 1h, 6h, 24h, or 7d")
    end = timestamp(end) if isinstance(end, str) else end
    # Retrospective imports can arrive after the window. This is NOT an as-known-then backtest.
    known_at = timestamp(known_at) if isinstance(known_at, str) else known_at or datetime.now(timezone.utc)
    if end > known_at:
        raise ValueError("Window end must not exceed the collection cutoff")
    scopes = {r["query_scope"] for r in state["coverage"] if r["ticker"] == ticker and r["source"] == source}
    if query_scope is None:
        if len(scopes) > 1:
            raise ValueError("Multiple query scopes; choose one explicitly")
        query_scope = next(iter(scopes), "unspecified")
    width = timedelta(hours=WINDOWS[window])
    posts = [r for r in state["posts"] if r["resolved_ticker"] == ticker and r["source"] == source
             and r["query_scope"] == query_scope
             and timestamp(r["collected_at"]) <= known_at]
    def sample(a, b):
        return [r for r in posts if a <= timestamp(r["published_at"]) < b]
    def authors(rows):
        return Counter(r["author_hash"] for r in rows if r["author_hash"])
    start = end - width
    current = sample(start, end)
    status = coverage_status(state, ticker, source, start, end, known_at, query_scope)
    baseline = []
    for i in range(1, 5):
        a, b = start - width * i, start - width * (i - 1)
        if coverage_status(state, ticker, source, a, b, known_at, query_scope) == "complete":
            baseline.append(sample(a, b))
    counts = authors(current)
    n = len(current)
    texts = Counter(re.sub(r"\s+", " ", r["text"].casefold()).strip() for r in current)
    links = Counter(link for r in current for link in set(re.findall(r"https?://[^\s]+", r["text"])))
    minutes = Counter(timestamp(r["published_at"]).replace(second=0, microsecond=0) for r in current)
    sufficient = len(baseline) == 4
    average = mean(len(b) for b in baseline) if sufficient else None
    author_average = mean(len(authors(b)) for b in baseline) if sufficient else None
    author_complete = all(r["author_hash"] for rows in [current] + baseline for r in rows)
    values = {"mention_growth": n / average if average else None,
              "author_growth": len(counts) / author_average if author_average and author_complete else None,
              "author_concentration": max(counts.values()) / n if counts and author_complete else None,
              "repeated_text": sum(v for v in texts.values() if v > 1) / n if n else 0,
              "shared_link": max(links.values()) / n if links else 0,
              "minute_concentration": max(minutes.values()) / n if n else 0}
    score = None
    components = []
    if status == "complete" and sufficient and average and author_complete:
        for name, (threshold, points) in RULES.items():
            value = values[name]
            awarded = points if n >= 5 and value is not None and value >= threshold else 0
            components.append({"feature": name, "value": value, "threshold": threshold, "points": awarded})
        score = sum(r["points"] for r in components)
    baseline_status = "insufficient_baseline" if not sufficient else "zero_baseline" if not average else "available"
    label = "Insufficient coverage" if status != "complete" else "Insufficient baseline" if baseline_status != "available" else "Insufficient author data" if not author_complete else "Elevated attention" if score >= 50 else "Normal"
    return {"ticker": ticker, "source": source, "query_scope": query_scope, "window": window,
            "start": start.isoformat(), "end": end.isoformat(), "collection_cutoff": known_at.isoformat(),
            "data_kind": state["data_kind"], "analysis_mode": "retrospective_import",
            "coverage_status": status, "confirmed_zero": status == "complete" and n == 0,
            "mention_count_observed": n, "unique_authors_observed": len(counts),
            "baseline_status": baseline_status, "baseline_windows": len(baseline),
            "baseline_mean_mentions": average, "baseline_mean_authors": author_average,
            "values": values, "social_attention_score": score, "score_version": SCORE_VERSION,
            "label": label, "components": components}


def social_features(ticker, source, end, workspace=DEFAULT_WORKSPACE, window="24h", query_scope=None):
    with writer_lock(workspace):
        state = read_state(workspace)
        result = features(state, ticker, source, end, window, query_scope)
        result["generated_at"] = now()
        result["id"] = secrets.token_hex(16)
        state["evaluations"].append(result)
        save_json(Path(workspace) / "social.json", state)
    return result


def timeline(workspace, ticker):
    """Evidence chronology; recorded market observations retain their actual capture time."""
    from .storage import read_csv
    ticker = symbol(ticker)
    state = read_state(workspace)
    events = []
    for row in state["posts"]:
        if row["resolved_ticker"] == ticker:
            events.append({"event_at": row["published_at"], "type": "social_post",
                           "collected_at": row["collected_at"], "recorded_at": row["imported_at"],
                           "source": row["source"], "url": row["url"], "text": row["text"]})
    for row in state["evaluations"]:
        if row["ticker"] == ticker:
            events.append({"event_at": row["generated_at"], "type": "social_evaluation",
                           "window_end": row["end"], "source": row["source"],
                           "social_attention_score": row["social_attention_score"], "label": row["label"],
                           "analysis_mode": row["analysis_mode"]})
    market = read_csv(Path(workspace) / "observations.csv")
    if not market.empty:
        for row in market[market.ticker.eq(ticker)].to_dict("records"):
            events.append({"event_at": row["observed_at"], "type": "market_observation",
                           "session": row["session"], "market_status": row["scan_status"],
                           "market_score": row.get("pump_score"), "close": row.get("alert_price"),
                           "volume": row.get("volume"), "score_version": row["score_version"]})
    return {"ticker": ticker, "data_kind": state["data_kind"],
            "events": sorted(events, key=lambda r: timestamp(r["event_at"])),
            "coverage": [r for r in state["coverage"] if r["ticker"] == ticker]}


def social_demo(workspace=None):
    """Deterministic fictional activity; no downloads or real ticker assertions."""
    workspace = Path(workspace or ROOT / "runs/social_demo")
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError("Choose an empty demo workspace")
    universe_update(workspace, "DEMO", "Fictional demonstration only", issuer="Fictional Demo Company")
    end = datetime(2025, 11, 7, 18, tzinfo=timezone.utc)
    observations = []
    for day in range(1, 36):
        published = end - timedelta(days=day, hours=1)
        observations.append({"source": "fixture", "query_scope": "cashtag:DEMO",
            "source_post_id": f"baseline-{day}", "url": f"https://example.invalid/posts/base-{day}",
            "published_at": published.isoformat(), "collected_at": end.isoformat(),
            "text": f"$DEMO fictional baseline observation {day}", "author_id": f"baseline-{day}"})
    for i in range(12):
        published = end - timedelta(minutes=5, seconds=i)
        observations.append({"source": "fixture", "query_scope": "cashtag:DEMO",
            "source_post_id": f"burst-{i}", "url": f"https://example.invalid/posts/burst-{i}",
            "published_at": published.isoformat(), "collected_at": end.isoformat(),
            "text": "$DEMO fictional repeated promotion https://example.invalid/promotion", "author_id": f"author-{i}"})
    payload = {"schema_version": 1, "data_kind": "synthetic", "observations": observations,
        "coverage": [{"source": "fixture", "ticker": "DEMO", "query_scope": "cashtag:DEMO",
                      "start": (end - timedelta(days=36)).isoformat(), "end": end.isoformat(),
                      "collected_at": end.isoformat(), "status": "complete"}]}
    save_json(workspace / "example_import.json", payload)
    import_payload(workspace, payload)
    result = social_features("DEMO", "fixture", end.isoformat(), workspace)
    return {"workspace": str(workspace), "data_kind": "synthetic", "result": result}
