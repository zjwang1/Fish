"""
trading_calendar.py – US stock market trading-day helpers.

Rules (simplified):
  • Monday–Friday are trading days.
  • Saturday and Sunday are closed.
  • On a trading day the market is considered open **24 h** (Bit.com
    stock API allows extended-hours trading, and the strategy only
    needs to know whether *any* stock order can be placed that day).

The check uses **US Eastern time** (America/New_York) because that is
the reference timezone for NYSE / NASDAQ calendars.

Note: US public holidays (e.g. MLK Day, Independence Day) are NOT
currently excluded.  This keeps the implementation dependency-free
and is conservative – attempting a trade on a holiday will simply
fail at the Bit.com API level, which the retry logic already handles.
"""

from datetime import datetime, timezone, timedelta, tzinfo


# ── US Eastern timezone (manual, no dependency on ``zoneinfo``) ──────
# EDT = UTC-4, EST = UTC-5.  DST starts 2nd Sunday of March, ends
# 1st Sunday of November – but for weekday-only checks the 1-hour
# difference doesn't matter: a Saturday in EST is still a Saturday
# in EDT.  We use a fixed UTC-5 offset for simplicity.
_US_EASTERN_OFFSET = timezone(timedelta(hours=-5))


def _to_us_eastern(dt: datetime) -> datetime:
    """Convert a datetime to US Eastern (fixed UTC-5).

    If *dt* is naive, it is assumed to be UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_US_EASTERN_OFFSET)


def is_us_stock_trading_day(dt: datetime | None = None) -> bool:
    """Return *True* if *dt* falls on a US stock trading day (Mon–Fri).

    Uses US Eastern time for the weekday check.  If *dt* is ``None``,
    the current UTC time is used.

    Trading days are treated as 24 h – no intraday session check.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    eastern = _to_us_eastern(dt)
    # Monday=0 … Friday=4 → trading day;  Saturday=5, Sunday=6 → closed
    return eastern.weekday() < 5


def is_weekend(dt: datetime | None = None) -> bool:
    """Convenience inverse of ``is_us_stock_trading_day``."""
    return not is_us_stock_trading_day(dt)
