"""Versioned scanning/tracking workflows, with offline replay support."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import uuid
import pandas as pd
from . import SCORE_VERSION, OUTCOME_VERSION, THRESHOLD
from .calendar import completed_session, outcome_sessions, sessions_between
from .core import (normalize_bars, calculate_pump_score, explain, assign_tiers,
                   resolve_universe, outcome_from_bars, metrics)
from .storage import (ROOT, DEFAULT_WORKSPACE, writer_lock, save_csv, save_json, read_csv,
                      latest_historical_run, upsert_observations)


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def load_watchlist(path):
    path = Path(path)
    if not path.exists():
        return []
    tickers = sorted({line.split("#", 1)[0].strip().upper()
                      for line in path.read_text(encoding="utf-8-sig").splitlines()} - {""})
    for ticker in tickers:
        validate_ticker(ticker)
    return tickers


def validate_ticker(ticker):
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.^=-]{0,19}", ticker):
        raise ValueError(f"Invalid ticker: {ticker!r}")


def fetch_bars(ticker, start, end, prices_dir=None):
    """end is exclusive. Offline files must use one consistent adjustment basis."""
    validate_ticker(ticker)
    if prices_dir:
        base = Path(prices_dir)
        path = base / f"{ticker}.csv"
        if not path.exists():
            path = base / ticker / "signals.csv"
        raw = pd.read_csv(path)
    else:
        import yfinance as yf
        raw = yf.download(ticker, start=str(pd.Timestamp(start).date()),
                          end=str(pd.Timestamp(end).date()), auto_adjust=True,
                          actions=True, progress=False, timeout=20, threads=False)
    bars = normalize_bars(raw, ticker)
    return bars[(bars.index >= pd.Timestamp(start)) & (bars.index < pd.Timestamp(end))]


def record_bars(path, bars):
    text = bars.reset_index().to_csv(index=False)
    from .storage import atomic_text
    atomic_text(path, text)
    return sha256(text.encode("utf-8")).hexdigest()


def scan(workspace, session=None, historical_run=None, watchlist=None,
         mode="union_selected", prices_dir=None):
    workspace = Path(workspace).resolve()
    provider = "offline" if prices_dir else "yfinance"
    if prices_dir and workspace == DEFAULT_WORKSPACE.resolve():
        raise ValueError("Offline replay requires a separate --workspace (or use the demo command)")
    day = completed_session(session)
    daystr = str(day.date())
    watch = load_watchlist(watchlist or ROOT / "source/MAIN/watchlist.txt")
    history = None if mode == "override" else latest_historical_run(historical_run)
    tiers = {"tier1": [], "tier2": [], "tier3": []}
    if history:
        intervals = pd.read_csv(history / "data/analysis/ticker_intervals.csv")
        tiers = assign_tiers(intervals)
    universe = resolve_universe(tiers, watch, day, mode)
    if not universe:
        raise ValueError("Universe is empty; provide a populated watchlist or historical tiers")
    for item in universe:
        validate_ticker(item["ticker"])
    attempt_id = f"{daystr}_{uuid.uuid4().hex[:12]}"
    with writer_lock(workspace):
        metadata_path = workspace / "workspace.json"
        if metadata_path.exists():
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
            if existing.get("score_version") != SCORE_VERSION:
                raise ValueError("Use a separate workspace for this score version")
            if existing.get("provider", provider) != provider:
                raise ValueError("Offline and live observations require separate workspaces")
        if (workspace / "legacy_import.json").exists():
            raise ValueError("Live scans cannot be mixed into a reconstructed legacy cohort")
        folder = workspace / "attempts" / attempt_id
        manifest = {"schema_version": 2, "kind": "scan", "attempt_id": attempt_id,
                    "session": daystr, "started_at": utcnow(), "state": "running",
                    "score_version": SCORE_VERSION, "threshold": THRESHOLD,
                    "comparison": ">", "outcome_version": OUTCOME_VERSION,
                    "provider": "offline" if prices_dir else "yfinance",
                    "price_basis": "supplied_file" if prices_dir else "auto_adjust=True",
                    "historical_run": str(history) if history else None,
                    "universe": universe, "watchlist_mode": mode}
        save_json(folder / "manifest.json", manifest)
        rows = []
        start = day - pd.Timedelta(days=100)
        grid = sessions_between(start, day)
        for member in universe:
            ticker = member["ticker"]
            row = member | {"session": daystr, "alert_date": daystr, "score_version": SCORE_VERSION,
                            "attempt_id": attempt_id, "observed_at": utcnow(), "source": manifest["provider"]}
            try:
                bars = fetch_bars(ticker, start, day + pd.Timedelta(days=1), prices_dir)
                row["bars_sha256"] = record_bars(folder / "bars" / f"{ticker}.csv", bars)
                if bars.empty or day not in bars.index:
                    row.update(scan_status="stale", error="No bar for intended session")
                else:
                    scored = calculate_pump_score(bars.reindex(grid))
                    latest = scored.loc[day]
                    if not latest.eligible:
                        row.update(scan_status="invalid", error="Invalid bar or fewer than 21 valid baseline sessions")
                    else:
                        row.update(scan_status="alert" if latest.flag else "no_signal",
                                   pump_score=int(latest.pump_score), alert_price=float(latest.Close),
                                   volume=float(latest.Volume), explanation=json.dumps(explain(latest)),
                                   **{f: float(latest[f]) for f in ["vol_z", "vol_ratio", "vol_trend", "price_z", "gap_up", "volatility"]},
                                   daily_return=float(latest["return"]))
            except Exception as exc:
                row.update(scan_status="fetch_failed", error=f"{type(exc).__name__}: {exc}")
            rows.append(row)
            print(f"{ticker}: {row['scan_status']}")
            # Durable per-ticker progress remains inspectable after interruption.
            save_csv(folder / "observations.csv", pd.DataFrame(rows))
        observations = upsert_observations(read_csv(workspace / "observations.csv"), pd.DataFrame(rows))
        save_csv(workspace / "observations.csv", observations)
        manifest.update(finished_at=utcnow(), state="complete" if all(
            r["scan_status"] in ["alert", "no_signal"] for r in rows) else "partial",
            counts=pd.Series([r["scan_status"] for r in rows]).value_counts().to_dict())
        save_json(folder / "manifest.json", manifest)
        save_json(workspace / "latest_scan.json", manifest)
        save_json(workspace / "workspace.json", {"schema_version": 2, "kind": "observatory", "score_version": SCORE_VERSION,
                                                "provider": provider})
        write_report(workspace)
    return manifest


def alerts_with_outcomes(workspace):
    obs = read_csv(Path(workspace) / "observations.csv")
    if obs.empty:
        return pd.DataFrame(columns=["ticker", "session", "score_version", "pump_score", "state", "outcome"])
    alerts = obs[obs.scan_status.eq("alert")].copy()
    outcomes = read_csv(Path(workspace) / "outcomes.csv")
    if not outcomes.empty:
        alerts = alerts.merge(outcomes, on=["ticker", "session", "score_version"], how="left", validate="one_to_one")
    for col, default in [("state", "provisional"), ("outcome", "pending")]:
        if col not in alerts:
            alerts[col] = default
        else:
            alerts[col] = alerts[col].fillna(default)
    return alerts


def track(workspace, as_of=None, prices_dir=None):
    workspace = Path(workspace).resolve()
    day = completed_session(as_of)
    attempt_id = f"track_{day.date()}_{uuid.uuid4().hex[:12]}"
    with writer_lock(workspace):
        marker = workspace / "workspace.json"
        if marker.exists():
            meta = json.loads(marker.read_text(encoding="utf-8"))
            if meta.get("provider") and meta["provider"] != ("offline" if prices_dir else "yfinance"):
                raise ValueError("Use the same offline/live source mode as this workspace's observations")
        alerts = alerts_with_outcomes(workspace)
        previous = read_csv(workspace / "outcomes.csv")
        stored = {} if previous.empty else {
            (r["ticker"], r["session"], r["score_version"]): r for r in previous.to_dict("records")}
        folder = workspace / "attempts" / attempt_id
        manifest = {"kind": "track", "attempt_id": attempt_id, "as_of": str(day.date()),
                    "started_at": utcnow(), "state": "running"}
        save_json(folder / "manifest.json", manifest)
        attempts = []
        changed = False
        cache = {}
        for ticker, group in alerts.groupby("ticker"):
            pending = group[group.state.ne("final") & pd.to_datetime(group.session).le(day)]
            if pending.empty:
                continue
            start = pd.to_datetime(pending.session).min()
            end = min(day + pd.Timedelta(days=1), pd.to_datetime(pending.session).max() + pd.Timedelta(days=46))
            try:
                cache[ticker] = fetch_bars(ticker, start, end, prices_dir)
                digest = record_bars(folder / "bars" / f"{ticker}.csv", cache[ticker])
                error = None
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            for alert in pending.to_dict("records"):
                key = (ticker, alert["session"], alert["score_version"])
                status = {"ticker": ticker, "session": alert["session"]}
                try:
                    if error:
                        raise ValueError(error)
                    outcome = outcome_from_bars(cache[ticker], alert["session"], outcome_sessions(alert["session"]), day)
                    status["data_status"] = outcome["data_status"]
                    old = stored.get(key, {})
                    # Failed fetches or older replays cannot erase valid observations.
                    if outcome["data_status"] in ["complete", "awaiting_sessions"] and (
                        not old or pd.Timestamp(old["as_of"]) <= day):
                        stored[key] = dict(zip(["ticker", "session", "score_version"], key)) | outcome | {
                            "as_of": str(day.date()), "updated_at": utcnow(), "bars_sha256": digest,
                            "attempt_id_outcome": attempt_id,
                            "evaluation_basis": "supplied_file" if prices_dir else "auto_adjust=True same-download entry and exits"}
                        changed = True
                except Exception as exc:
                    status.update(data_status="fetch_failed", error=str(exc))
                attempts.append(status)
        if changed:
            save_csv(workspace / "outcomes.csv", pd.DataFrame(stored.values()))
        save_json(folder / "updates.json", attempts)
        manifest.update(state="partial" if any(x["data_status"] not in ["complete", "awaiting_sessions"] for x in attempts) else "complete",
                        finished_at=utcnow(), updates=len(attempts))
        save_json(folder / "manifest.json", manifest)
        save_json(workspace / "latest_tracking.json", manifest)
        write_report(workspace)
    return manifest


def write_report(workspace):
    alerts = alerts_with_outcomes(workspace)
    summary = metrics(alerts)
    save_json(Path(workspace) / "summary.json", summary)
    save_csv(Path(workspace) / "alerts.csv", alerts)
    rate = "Not yet available" if summary["rate"] is None else f"{summary['rate']:.1f}%"
    from .storage import atomic_text
    atomic_text(Path(workspace) / "briefing.md", f"# Microcap Observatory\n\n"
                f"Generated: {utcnow()}\n\nAlerts: {summary['total']}\n\n"
                f"Final ten-session outcomes: {summary['final']}\n\nPending: {summary['pending']}\n\n"
                f"Sharp reversal share among final outcomes: {rate}\n\n"
                "Price-pattern outcomes do not establish manipulation.\n")


def report(workspace):
    return metrics(alerts_with_outcomes(workspace))


def import_legacy(source, workspace):
    """Separate reconstructed cohort; legacy outcome claims are not carried forward."""
    source, workspace = Path(source).resolve(), Path(workspace).resolve()
    df = pd.read_csv(source)
    required = {"ticker", "alert_date", "pump_score", "alert_price"}
    if not required.issubset(df.columns):
        raise ValueError(f"Missing columns: {required - set(df.columns)}")
    with writer_lock(workspace):
        marker = workspace / "legacy_import.json"
        if not read_csv(workspace / "observations.csv").empty or marker.exists():
            raise ValueError("Legacy import requires a new empty workspace")
        obs = df[[c for c in ["ticker", "tier", "alert_date", "pump_score", "alert_price", "volume", "vol_z", "daily_return"] if c in df]].copy()
        obs["session"] = pd.to_datetime(obs.alert_date).dt.strftime("%Y-%m-%d")
        obs["score_version"] = "legacy-unversioned"
        obs["scan_status"] = "alert"
        obs["source"] = "legacy-import"
        obs = obs.drop_duplicates(["ticker", "session", "score_version"])
        save_csv(workspace / "observations.csv", obs)
        save_json(marker, {"source": str(source), "sha256": sha256(source.read_bytes()).hexdigest(),
                           "imported_at": utcnow(), "rows": len(obs), "note": "Outcomes require reconstruction; original bars at alert time are unavailable."})
        save_json(workspace / "workspace.json", {"schema_version": 2, "kind": "legacy-reconstruction", "score_version": "legacy-unversioned"})
        write_report(workspace)
    return len(obs)


def demo(workspace=None):
    """Replay an archived session; no market requests or legacy-file changes."""
    workspace = Path(workspace or ROOT / "runs/demo_v2").resolve()
    if workspace.exists() and any(workspace.iterdir()):
        marker = workspace / "workspace.json"
        if not marker.exists() or json.loads(marker.read_text(encoding="utf-8")).get("kind") != "offline-demo":
            raise ValueError("Demo requires an empty workspace or an existing offline-demo workspace")
    source = ROOT / "runs/2025-11-07_2227_1y/data/signals_csv"
    paths = sorted(source.glob("*/signals.csv"))
    if not paths:
        # A fresh clone has no private/provider data. Generate fictional OHLCV.
        import numpy as np
        source = workspace / "synthetic_prices"
        dates = sessions_between("2025-07-01", "2025-11-07")
        close = 10 + np.sin(np.arange(len(dates))) * .02
        volume = np.full(len(dates), 10000)
        signal_idx = dates.get_loc(pd.Timestamp("2025-10-24"))
        close[signal_idx], volume[signal_idx] = 14, 1000000
        bars = pd.DataFrame({"Date": dates, "Open": close, "High": close * 1.01,
                             "Low": close * .99, "Close": close, "Volume": volume})
        save_csv(source / "DEMO.csv", bars)
        tickers = ["DEMO"]
        demo_source = "synthetic fictional data"
    else:
        tickers = [p.parent.name for p in paths]
        demo_source = "local archived historical bars"
    watch = workspace / "demo_watchlist.txt"
    from .storage import atomic_text
    atomic_text(watch, "\n".join(tickers) + "\n")
    result = scan(workspace, "2025-10-24", watchlist=watch, mode="override", prices_dir=source)
    track(workspace, "2025-11-07", prices_dir=source)
    save_json(workspace / "workspace.json", {"schema_version": 2, "kind": "offline-demo", "score_version": SCORE_VERSION,
                                            "provider": "offline", "demo_source": demo_source})
    return result
