"""
price_fetcher.py – Retrieve real-time prices for US stocks (via Bit.com)
and Binance futures, plus funding-rate data for funding-rate arbitrage.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from config import (
    BINANCE_API_KEY,
    BINANCE_API_SECRET,
    BINANCE_TESTNET,
    BITCOM_ACCESS_KEY,
    BITCOM_SECRET_KEY,
    BITCOM_BASE_URL,
)
from binance_client import BinanceFuturesClient
from bitcom_client import BitcomStockClient

logger = logging.getLogger(__name__)

# ── Binance client singleton ────────────────────────────────────────
_binance: Optional[BinanceFuturesClient] = None


def _get_binance() -> BinanceFuturesClient:
    """Return (and lazily create) a Binance Futures client."""
    global _binance
    if _binance is None:
        _binance = BinanceFuturesClient(
            api_key=BINANCE_API_KEY,
            api_secret=BINANCE_API_SECRET,
            testnet=BINANCE_TESTNET,
        )
        mode = "TESTNET" if BINANCE_TESTNET else "LIVE"
        logger.info("Binance Futures client initialised (%s)", mode)
    return _binance


# ── Bit.com stock client singleton ───────────────────────────────────
_bitcom_client: Optional[BitcomStockClient] = None


def _get_bitcom_client() -> BitcomStockClient:
    """Return (and lazily create) a Bit.com Stock API client."""
    global _bitcom_client
    if _bitcom_client is None:
        _bitcom_client = BitcomStockClient(
            access_key=BITCOM_ACCESS_KEY,
            secret_key=BITCOM_SECRET_KEY,
            base_url=BITCOM_BASE_URL,
        )
        logger.info("Bit.com Stock client initialised (base=%s)", BITCOM_BASE_URL)
    return _bitcom_client


def get_bitcom_client() -> BitcomStockClient:
    """Public accessor for the Bit.com client (used by trader.py)."""
    return _get_bitcom_client()


def get_binance_client() -> BinanceFuturesClient:
    """Public accessor for the Binance Futures client (used by trader.py)."""
    return _get_binance()


# ── Data containers ──────────────────────────────────────────────────

@dataclass
class FundingInfo:
    """Funding-rate snapshot for a Binance perpetual contract."""
    current_rate: float          # e.g. 0.0001 = 0.01 %
    next_funding_time: Optional[datetime]
    mark_price: Optional[float]
    index_price: Optional[float]


# ── Public helpers ───────────────────────────────────────────────────

def get_stock_price(symbol: str) -> Optional[float]:
    """Fetch the latest price for a US stock via Bit.com Stock API.

    *symbol* should be in Bit.com format, e.g. ``"MU.US"``.
    Returns *None* if the data is unavailable.
    """
    try:
        client = _get_bitcom_client()
        quote = client.get_quote(symbol)
        if quote is not None and quote.last_price > 0:
            logger.debug("Stock %s price (Bit.com): %.4f", symbol, quote.last_price)
            return quote.last_price
        return None
    except Exception:
        logger.exception("Failed to fetch stock price for %s via Bit.com", symbol)
        return None


def get_futures_price(symbol: str) -> Optional[float]:
    """Fetch the latest price for a Binance perpetual futures contract.

    *symbol* is e.g. ``MU/USDT:USDT`` (unified) or ``MUUSDT`` (raw).
    """
    try:
        client = _get_binance()
        price = client.get_ticker_price(symbol)
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
        client = _get_binance()
        data = client.get_mark_price(symbol)

        rate_str = data.get("lastFundingRate")
        if rate_str is None:
            return None
        rate = float(rate_str)

        next_ts = int(data.get("nextFundingTime", 0))
        next_dt: Optional[datetime] = None
        if next_ts > 0:
            next_dt = datetime.fromtimestamp(next_ts / 1000, tz=timezone.utc)

        mark = float(data.get("markPrice", 0)) or None
        index = float(data.get("indexPrice", 0)) or None

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

    Returns a list of dicts with keys ``fundingTime``, ``fundingRate``, etc.
    Useful for computing the average funding rate over the past N periods.
    """
    try:
        client = _get_binance()
        history = client.get_funding_rate_history(symbol, limit=limit)
        # Normalise keys to match what spread_monitor expects
        normalised = []
        for h in history:
            normalised.append({
                "timestamp": int(h.get("fundingTime", 0)),
                "fundingRate": float(h.get("fundingRate", 0)),
                "markPrice": float(h.get("markPrice", 0)) if h.get("markPrice") else None,
            })
        logger.debug("Fetched %d funding-rate records for %s", len(normalised), symbol)
        return normalised
    except Exception:
        logger.exception("Failed to fetch funding rate history for %s", symbol)
        return []
