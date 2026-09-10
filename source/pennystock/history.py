"""Historical replay and descriptive activity episodes, using the live engine."""
from pathlib import Path
import uuid
import numpy as np
import pandas as pd
from . import SCORE_VERSION, OUTCOME_VERSION
from .calendar import completed_session, sessions_between, outcome_sessions
from .core import calculate_pump_score, outcome_from_bars
from .pipeline import fetch_bars, load_watchlist, utcnow
from .storage import ROOT, save_csv, save_json, latest_historical_run

DEFAULT_TICKERS = "FEMY NAKA MBRX AGL CHGG IXHL MODD PSNY SHOT IPSC AIRE OPI NWTN SGMO ACET PPBT AZI MOBX PCSA CENN ARBK ICCM LBGJ PRPL VRME ATCH ORIS PFSA HBIO XHLD VSEE EHGO".split()


def analyze_episodes(master, run):
    run = Path(run)
    df = master.sort_values(["ticker", "signal_date"]).copy()
    df["signal_date"] = pd.to_datetime(df.signal_date)
    gap = df.groupby("ticker").signal_date.diff().dt.days
    df["episode_number"] = (gap.isna() | gap.gt(7)).groupby(df.ticker).cumsum()
    df["episode_key"] = df.ticker + "_E" + df.episode_number.astype(str)
    episodes = df.groupby(["ticker", "episode_key"]).agg(
        start_date=("signal_date", "min"), end_date=("signal_date", "max"),
        signal_count=("signal_date", "size"), avg_pump_score=("pump_score", "mean"),
        reversal_count=("classification", lambda x: int(x.eq("sharp_reversal").sum()))).reset_index()
    intervals = []
    for ticker, group in episodes.groupby("ticker"):
        group = group.sort_values("start_date")
        gaps = (group.start_date - group.end_date.shift()).dt.days.dropna()
        if len(gaps) >= 2:
            mean = float(gaps.mean())
            intervals.append({"ticker": ticker, "num_episodes": len(group), "avg_gap_days": mean,
                              "coefficient_variation": float(np.std(gaps) / mean) if mean else 0,
                              "last_episode": str(group.end_date.max().date()),
                              "interval_sample_size": len(gaps)})
    columns = ["ticker", "num_episodes", "avg_gap_days", "coefficient_variation", "last_episode", "interval_sample_size"]
    save_csv(run / "data/analysis/ticker_intervals.csv", pd.DataFrame(intervals, columns=columns))
    save_csv(run / "data/signals_csv/ACTIVITY_EPISODES.csv", episodes)
    save_csv(run / "data/signals_csv/MASTER_OUTCOMES.csv", df)
    return episodes


def backtest(start=None, end=None, tickers=None, prices_dir=None, run_name=None):
    end = completed_session(end)
    start = pd.Timestamp(start) if start else end - pd.Timedelta(days=365)
    if start >= end:
        raise ValueError("Start must precede end")
    if run_name and (Path(run_name).name != run_name or run_name in {".", ".."}):
        raise ValueError("Run name must be a single folder name")
    run = ROOT / "runs" / (run_name or f"{end.date()}_{uuid.uuid4().hex[:8]}_v2_backtest")
    if run.exists():
        raise ValueError("Historical output must be a new run directory")
    tickers = sorted(set(tickers or DEFAULT_TICKERS))
    manifest = {"kind": "backtest", "state": "running", "score_version": SCORE_VERSION,
                "outcome_version": OUTCOME_VERSION, "start": str(start.date()), "end": str(end.date()),
                "created_at": utcnow(), "source": "offline" if prices_dir else "yfinance",
                "universe": tickers, "note": "Retrospective selected-universe research; not an untouched forward evaluation."}
    save_json(run / "manifest.json", manifest)
    results, statuses = [], []
    grid = sessions_between(start, end)
    for ticker in tickers:
        try:
            bars = fetch_bars(ticker, start, end + pd.Timedelta(days=1), prices_dir).reindex(grid)
            scored = calculate_pump_score(bars)
            save_csv(run / "data/signals_csv" / ticker / "signals.csv", scored.reset_index(names="Date"))
            for date, signal in scored[scored.flag].iterrows():
                outcome = outcome_from_bars(bars, date, outcome_sessions(date), end)
                results.append({"ticker": ticker, "signal_date": str(date.date()),
                                "entry_price": float(signal.Close), "pump_score": int(signal.pump_score),
                                "signal_return": float(signal["return"]), "vol_z": float(signal.vol_z),
                                "score_version": SCORE_VERSION, "classification": outcome["outcome"], **outcome})
            eligible_count = int(scored.eligible.sum())
            statuses.append({"ticker": ticker, "status": "complete" if eligible_count else "invalid",
                             "eligible_bars": eligible_count})
        except Exception as exc:
            statuses.append({"ticker": ticker, "status": "failed", "error": str(exc)})
    master = pd.DataFrame(results) if results else pd.DataFrame(columns=["ticker", "signal_date", "pump_score", "classification"])
    analyze_episodes(master, run)
    save_csv(run / "data/analysis/ticker_status.csv", pd.DataFrame(statuses))
    manifest.update(state="partial" if any(s["status"] != "complete" for s in statuses) else "complete",
                    signals=len(results), finished_at=utcnow(), statuses=statuses)
    save_json(run / "manifest.json", manifest)
    print(f"Historical analysis saved to {run}")
    return manifest


def analyze_existing(run=None):
    run = latest_historical_run(run)
    path = run / "data/signals_csv/MASTER_OUTCOMES.csv"
    if not path.exists():
        raise ValueError("Legacy analysis is preserved. Run pump_detector.py to create a v2 historical dataset first.")
    return analyze_episodes(pd.read_csv(path), run)
