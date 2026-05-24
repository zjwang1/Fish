"""
price_fetcher.py – Retrieve real-time prices for US stocks and Binance futures,
plus funding-rate data needed for the funding-rate-arbitrage strategy.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import ccxt
import yfinance as yf

from config import BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_TESTNET

logger = logging.getLogger(__name__)

# ── Binance exchange singleton ───────────────────────────────────────
_exchange: Optional[ccxt.binance] = None


def _get_exchange() -> ccxt.binance:
    """Return (and lazily create) a ccxt Binance Futures client."""
    global _exchange
    if _exchange is None:
        _exchange = ccxt.binance(
            {
                "apiKey": BINANCE_API_KEY,
                "secret": BINANCE_API_SECRET,
                "options": {"defaultType": "future"},
                "enableRateLimit": True,
            }
        )
        if BINANCE_TESTNET:
            _exchange.set_sandbox_mode(True)
            logger.info("Binance client running in TESTNET mode")
        _exchange.load_markets()
    return _exchange


# ── Data containers ──────────────────────────────────────────────────

@dataclass
class FundingInfo:
    """Funding-rate snapshot for a Binance perpetual contract."""
    current_rate: float          # e.g. 0.0001 = 0.01 %
    next_funding_time: Optional[datetime]
    mark_price: Optional[float]
    index_price: Optional[float]


# ── Public helpers ───────────────────────────────────────────────────

def get_stock_price(ticker: str) -> Optional[float]:
    """Fetch the latest price for a US stock via Yahoo Finance.

    Returns *None* if the data is unavailable (market closed, bad ticker, etc.).
    """
    try:
        tk = yf.Ticker(ticker)
        info = tk.fast_info
        price = getattr(info, "last_price", None)
        if price is None:
            price = getattr(info, "previous_close", None)
        if price is not None:
            logger.debug("Stock %s price: %.4f", ticker, price)
        return price
    except Exception:
        logger.exception("Failed to fetch stock price for %s", ticker)
        return None


def get_futures_price(symbol: str) -> Optional[float]:
    """Fetch the latest price for a Binance perpetual futures contract.

    *symbol* is a ccxt unified symbol, e.g. ``MU/USDT:USDT``.
    """
    try:
        exchange = _get_exchange()
        ticker = exchange.fetch_ticker(symbol)
        price = ticker.get("last") or ticker.get("close")
        if price is not None:
            logger.debug("Futures %s price: %.4f", symbol, price)
        return price
    except Exception:
        logger.exception("Failed to fetch futures price for %s", symbol)
        return None


def get_funding_info(symbol: str) -> Optional[FundingInfo]:
    """Fetch current funding rate + next funding time for a Binance perp.

    Returns a ``FundingInfo`` dataclass or *None* on failure.
    """
    try:
        exchange = _get_exchange()
        fr = exchange.fetch_funding_rate(symbol)

        rate = fr.get("fundingRate")
        if rate is None:
            return None

        next_ts = fr.get("fundingDatetime") or fr.get("nextFundingDatetime")
        next_dt: Optional[datetime] = None
        if isinstance(next_ts, str):
            next_dt = datetime.fromisoformat(next_ts.replace("Z", "+00:00"))
        elif isinstance(next_ts, (int, float)):
            next_dt = datetime.fromtimestamp(next_ts / 1000, tz=timezone.utc)

        mark = fr.get("markPrice")
        index = fr.get("indexPrice")

        logger.debug(
            "Funding %s: rate=%.6f  next=%s  mark=%s  index=%s",
            symbol, rate, next_dt, mark, index,
        )
        return FundingInfo(
            current_rate=rate,
            next_funding_time=next_dt,
            mark_price=mark,
            index_price=index,
        )
    except Exception:
        logger.exception("Failed to fetch funding info for %s", symbol)
        return None


def get_funding_rate_history(
    symbol: str, *, limit: int = 30
) -> list[dict]:
    """Fetch recent funding-rate history for a Binance perpetual.

    Returns a list of dicts with keys ``timestamp``, ``fundingRate``, etc.
    Useful for computing the average funding rate over the past N periods.
    """
    try:
        exchange = _get_exchange()
        history = exchange.fetch_funding_rate_history(symbol, limit=limit)
        logger.debug("Fetched %d funding-rate records for %s", len(history), symbol)
        return history
    except Exception:
        logger.exception("Failed to fetch funding rate history for %s", symbol)
        return []
