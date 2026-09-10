"""Atomic versioned CSV state, immutable attempts, and a shared writer lock."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKSPACE = ROOT / "runs" / "observatory_v2"


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".writing-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def save_json(path, value):
    atomic_text(path, json.dumps(value, indent=2, default=str, allow_nan=False))


def save_csv(path, df):
    atomic_text(path, df.to_csv(index=False))


def read_csv(path):
    return pd.read_csv(path, float_precision="round_trip") if Path(path).exists() else pd.DataFrame()


@contextmanager
def writer_lock(workspace):
    workspace = Path(workspace).resolve()
    # Never let new commands write into a legacy research run.
    if (workspace / "data").exists():
        raise ValueError("Choose a new workspace, not an existing legacy run")
    workspace.mkdir(parents=True, exist_ok=True)
    lock = workspace / ".writer.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError(f"Another writer holds {lock}. If it crashed, verify its process has stopped before removing the lock.") from None
    try:
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        yield
    finally:
        lock.unlink()


def latest_historical_run(explicit=None):
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = ROOT / path
        if not (path / "data/analysis/ticker_intervals.csv").exists():
            raise ValueError(f"No historical interval table in {path}")
        return path
    candidates = sorted((ROOT / "runs").glob("*/data/analysis/ticker_intervals.csv"))
    if not candidates:
        raise FileNotFoundError("Run historical analysis first, or supply a watchlist with --watchlist-mode override")
    return candidates[-1].parents[2]


def upsert_observations(previous, new):
    """Successful observations are immutable; failed observations may be retried."""
    if previous.empty:
        return new.drop_duplicates(["ticker", "session", "score_version"])
    successful = previous[previous.scan_status.isin(["alert", "no_signal"])]
    failed = previous[~previous.scan_status.isin(["alert", "no_signal"])]
    return pd.concat([successful, new, failed], ignore_index=True).drop_duplicates(
        ["ticker", "session", "score_version"], keep="first")
