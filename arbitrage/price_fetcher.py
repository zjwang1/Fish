"""
price_fetcher.py – Retrieve real-time prices for US stocks and Binance futures.
"""

import logging
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


# ── Public helpers ───────────────────────────────────────────────────

def get_stock_price(ticker: str) -> Optional[float]:
    """Fetch the latest price for a US stock / ETF via Yahoo Finance.

    Returns *None* if the data is unavailable (market closed, bad ticker, etc.).
    """
    try:
        tk = yf.Ticker(ticker)
        info = tk.fast_info
        price = getattr(info, "last_price", None)
        if price is None:
            # Fallback: try the previous close
            price = getattr(info, "previous_close", None)
        if price is not None:
            logger.debug("Stock %s price: %.4f", ticker, price)
        return price
    except Exception:
        logger.exception("Failed to fetch stock price for %s", ticker)
        return None


def get_futures_price(symbol: str) -> Optional[float]:
    """Fetch the latest mark price for a Binance perpetual futures contract.

    *symbol* should be a ccxt unified symbol, e.g. ``BTC/USDT:USDT``.
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


def get_funding_rate(symbol: str) -> Optional[float]:
    """Fetch the current funding rate for a Binance perpetual contract."""
    try:
        exchange = _get_exchange()
        fr = exchange.fetch_funding_rate(symbol)
        rate = fr.get("fundingRate")
        if rate is not None:
            logger.debug("Funding rate %s: %.6f", symbol, rate)
        return rate
    except Exception:
        logger.exception("Failed to fetch funding rate for %s", symbol)
        return None
