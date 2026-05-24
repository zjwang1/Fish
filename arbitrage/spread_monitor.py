"""
spread_monitor.py – Compute and track the spread between US stocks and
Binance futures, and emit signals when the spread exceeds the threshold.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from config import ArbPair, SPREAD_THRESHOLD
from price_fetcher import get_stock_price, get_futures_price, get_funding_rate

logger = logging.getLogger(__name__)


@dataclass
class SpreadSnapshot:
    """One point-in-time observation of a pair's spread."""
    timestamp: datetime
    pair: ArbPair
    stock_price: float
    futures_price: float
    implied_stock_crypto: float   # stock_price / hedge_ratio → "implied crypto price from stock side"
    spread_pct: float             # (implied - futures) / futures * 100
    funding_rate: Optional[float]
    signal: str                   # "LONG_STOCK_SHORT_FUTURES" | "SHORT_STOCK_LONG_FUTURES" | "NEUTRAL"


def compute_spread(pair: ArbPair) -> Optional[SpreadSnapshot]:
    """Fetch prices and compute the spread for one arbitrage pair."""
    stock_price = get_stock_price(pair.stock_ticker)
    futures_price = get_futures_price(pair.futures_symbol)

    if stock_price is None or futures_price is None:
        logger.warning(
            "Skipping %s – missing price (stock=%s, futures=%s)",
            pair.stock_ticker, stock_price, futures_price,
        )
        return None

    if pair.hedge_ratio == 0:
        logger.error("hedge_ratio for %s is 0 – cannot compute spread", pair.stock_ticker)
        return None

    # Implied crypto price from the stock side
    implied = stock_price / pair.hedge_ratio
    spread_pct = (implied - futures_price) / futures_price * 100.0

    # Determine signal
    if spread_pct > SPREAD_THRESHOLD:
        signal = "LONG_STOCK_SHORT_FUTURES"
    elif spread_pct < -SPREAD_THRESHOLD:
        signal = "SHORT_STOCK_LONG_FUTURES"
    else:
        signal = "NEUTRAL"

    funding_rate = get_funding_rate(pair.futures_symbol)

    snap = SpreadSnapshot(
        timestamp=datetime.now(timezone.utc),
        pair=pair,
        stock_price=stock_price,
        futures_price=futures_price,
        implied_stock_crypto=implied,
        spread_pct=spread_pct,
        funding_rate=funding_rate,
        signal=signal,
    )
    return snap


def format_snapshot(snap: SpreadSnapshot) -> str:
    """Pretty-print a SpreadSnapshot for terminal display."""
    fr_str = f"{snap.funding_rate * 100:.4f}%" if snap.funding_rate is not None else "N/A"
    return (
        f"[{snap.timestamp:%Y-%m-%d %H:%M:%S UTC}] "
        f"{snap.pair.stock_ticker:6s} ${snap.stock_price:>10.2f}  |  "
        f"{snap.pair.futures_symbol:16s} ${snap.futures_price:>10.2f}  |  "
        f"Implied ${snap.implied_stock_crypto:>10.2f}  |  "
        f"Spread {snap.spread_pct:+.2f}%  |  "
        f"FR {fr_str}  |  "
        f"Signal: {snap.signal}"
    )
