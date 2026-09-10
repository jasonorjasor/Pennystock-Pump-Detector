"""NYSE regular sessions, including holidays and early closes."""
from functools import lru_cache
import pandas as pd


@lru_cache(maxsize=1)
def calendar():
    import pandas_market_calendars as mcal
    return mcal.get_calendar("NYSE")


def sessions_between(start, end):
    return calendar().schedule(start_date=start, end_date=end).index


def outcome_sessions(day):
    day = pd.Timestamp(day)
    return sessions_between(day, day + pd.Timedelta(days=45))[:11]


def completed_session(requested=None, now=None, delay_minutes=30):
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        raise ValueError("Current time must be timezone-aware")
    now = now.tz_convert("UTC")
    day = pd.Timestamp(requested) if requested else now.tz_convert("America/New_York").tz_localize(None).normalize()
    schedule = calendar().schedule(start_date=day - pd.Timedelta(days=15), end_date=day)
    complete = schedule[schedule.market_close + pd.Timedelta(minutes=delay_minutes) <= now]
    if requested and (day.normalize() not in complete.index):
        raise ValueError("Requested session is a holiday, future session, or not yet complete (30-minute buffer)")
    if complete.empty:
        raise ValueError("No completed session available")
    return complete.index[-1]
