"""
trader.py – Execution module for funding-rate arbitrage.

Handles opening and closing hedged positions:
  • OPEN  = Buy stock on Bit.com  +  Short futures on Binance
  • CLOSE = Sell stock on Bit.com  +  Close (buy) futures on Binance

This module does NOT make autonomous trading decisions – it only executes
orders when explicitly called by the main loop or CLI.
"""

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import ccxt

from config import (
    ArbPair,
    BINANCE_API_KEY,
    BINANCE_API_SECRET,
    BINANCE_TESTNET,
    DEFAULT_TRADE_QTY,
)
from bitcom_client import BitcomStockClient, SIDE_BUY, SIDE_SELL, ORDER_TYPE_LIMIT
from price_fetcher import get_bitcom_client

logger = logging.getLogger(__name__)


# ── Data containers ──────────────────────────────────────────────────

@dataclass
class TradeResult:
    """Result of an arbitrage trade (one leg or both)."""
    timestamp: datetime
    pair: ArbPair
    action: str              # "OPEN" or "CLOSE"
    stock_order_id: str
    stock_side: str
    stock_qty: int
    stock_price: Optional[float]
    futures_order_id: str
    futures_side: str
    futures_qty: float
    futures_price: Optional[float]
    success: bool
    error: str = ""


# ── Binance futures trading ──────────────────────────────────────────

_futures_exchange: Optional[ccxt.binance] = None


def _get_futures_exchange() -> ccxt.binance:
    """Return a ccxt Binance Futures client for trading."""
    global _futures_exchange
    if _futures_exchange is None:
        _futures_exchange = ccxt.binance(
            {
                "apiKey": BINANCE_API_KEY,
                "secret": BINANCE_API_SECRET,
                "options": {"defaultType": "future"},
                "enableRateLimit": True,
            }
        )
        if BINANCE_TESTNET:
            _futures_exchange.set_sandbox_mode(True)
        _futures_exchange.load_markets()
    return _futures_exchange


def _short_futures(
    symbol: str,
    qty: float,
    price: Optional[float] = None,
) -> dict:
    """Open a SHORT position on Binance perpetual futures.

    Uses a limit order if *price* is given, otherwise a market order.
    """
    exchange = _get_futures_exchange()
    order_type = "limit" if price else "market"
    order = exchange.create_order(
        symbol=symbol,
        type=order_type,
        side="sell",
        amount=qty,
        price=price,
    )
    logger.info(
        "Futures SHORT: %s qty=%.4f price=%s → id=%s",
        symbol, qty, price, order.get("id"),
    )
    return order


def _close_short_futures(
    symbol: str,
    qty: float,
    price: Optional[float] = None,
) -> dict:
    """Close a SHORT position by buying back on Binance futures."""
    exchange = _get_futures_exchange()
    order_type = "limit" if price else "market"
    order = exchange.create_order(
        symbol=symbol,
        type=order_type,
        side="buy",
        amount=qty,
        price=price,
        params={"reduceOnly": True},
    )
    logger.info(
        "Futures CLOSE SHORT: %s qty=%.4f price=%s → id=%s",
        symbol, qty, price, order.get("id"),
    )
    return order


# ── Combined arbitrage trades ────────────────────────────────────────

def open_arb_position(
    pair: ArbPair,
    qty: int = 0,
    stock_price: Optional[float] = None,
    futures_price: Optional[float] = None,
) -> TradeResult:
    """Open a hedged position: BUY stock (Bit.com) + SHORT futures (Binance).

    Args:
        pair: The arbitrage pair to trade.
        qty: Number of shares to buy (uses DEFAULT_TRADE_QTY if 0).
        stock_price: Limit price for the stock order (None = market).
        futures_price: Limit price for the futures short (None = market).

    Returns:
        A ``TradeResult`` describing both legs.
    """
    if qty <= 0:
        qty = DEFAULT_TRADE_QTY

    futures_qty = qty * pair.shares_per_contract
    now = datetime.now(timezone.utc)
    stock_order_id = ""
    futures_order_id = ""
    error = ""

    try:
        # Leg 1: Buy stock on Bit.com
        client = get_bitcom_client()
        stock_order = client.place_order(
            symbol=pair.stock_symbol,
            side=SIDE_BUY,
            qty=qty,
            price=stock_price,
            order_type=ORDER_TYPE_LIMIT if stock_price else "MO",
            remark=f"arb-open-{pair.ticker}",
        )
        stock_order_id = stock_order.order_id
        logger.info("Stock BUY placed: %s qty=%d → %s", pair.stock_symbol, qty, stock_order_id)
    except Exception as e:
        error = f"Stock leg failed: {e}"
        logger.exception("Failed to buy stock %s", pair.stock_symbol)
        return TradeResult(
            timestamp=now, pair=pair, action="OPEN",
            stock_order_id="", stock_side=SIDE_BUY,
            stock_qty=qty, stock_price=stock_price,
            futures_order_id="", futures_side="sell",
            futures_qty=futures_qty, futures_price=futures_price,
            success=False, error=error,
        )

    try:
        # Leg 2: Short futures on Binance
        fut_order = _short_futures(pair.futures_symbol, futures_qty, futures_price)
        futures_order_id = fut_order.get("id", "")
    except Exception as e:
        error = f"Futures leg failed (stock already placed!): {e}"
        logger.exception(
            "Failed to short futures %s – STOCK ORDER %s IS LIVE, manual intervention needed!",
            pair.futures_symbol, stock_order_id,
        )

    success = bool(stock_order_id and futures_order_id and not error)
    return TradeResult(
        timestamp=now, pair=pair, action="OPEN",
        stock_order_id=stock_order_id, stock_side=SIDE_BUY,
        stock_qty=qty, stock_price=stock_price,
        futures_order_id=futures_order_id, futures_side="sell",
        futures_qty=futures_qty, futures_price=futures_price,
        success=success, error=error,
    )


def close_arb_position(
    pair: ArbPair,
    qty: int = 0,
    stock_price: Optional[float] = None,
    futures_price: Optional[float] = None,
) -> TradeResult:
    """Close a hedged position: SELL stock (Bit.com) + BUY-BACK futures (Binance).

    Args:
        pair: The arbitrage pair to close.
        qty: Number of shares to sell (uses DEFAULT_TRADE_QTY if 0).
        stock_price: Limit price for the stock sell (None = market).
        futures_price: Limit price for the futures buy-back (None = market).

    Returns:
        A ``TradeResult`` describing both legs.
    """
    if qty <= 0:
        qty = DEFAULT_TRADE_QTY

    futures_qty = qty * pair.shares_per_contract
    now = datetime.now(timezone.utc)
    stock_order_id = ""
    futures_order_id = ""
    error = ""

    try:
        # Leg 1: Sell stock on Bit.com
        client = get_bitcom_client()
        stock_order = client.place_order(
            symbol=pair.stock_symbol,
            side=SIDE_SELL,
            qty=qty,
            price=stock_price,
            order_type=ORDER_TYPE_LIMIT if stock_price else "MO",
            remark=f"arb-close-{pair.ticker}",
        )
        stock_order_id = stock_order.order_id
        logger.info("Stock SELL placed: %s qty=%d → %s", pair.stock_symbol, qty, stock_order_id)
    except Exception as e:
        error = f"Stock sell leg failed: {e}"
        logger.exception("Failed to sell stock %s", pair.stock_symbol)
        return TradeResult(
            timestamp=now, pair=pair, action="CLOSE",
            stock_order_id="", stock_side=SIDE_SELL,
            stock_qty=qty, stock_price=stock_price,
            futures_order_id="", futures_side="buy",
            futures_qty=futures_qty, futures_price=futures_price,
            success=False, error=error,
        )

    try:
        # Leg 2: Close short futures on Binance
        fut_order = _close_short_futures(pair.futures_symbol, futures_qty, futures_price)
        futures_order_id = fut_order.get("id", "")
    except Exception as e:
        error = f"Futures close leg failed (stock sell already placed!): {e}"
        logger.exception(
            "Failed to close futures %s – STOCK SELL %s IS LIVE, manual intervention needed!",
            pair.futures_symbol, stock_order_id,
        )

    success = bool(stock_order_id and futures_order_id and not error)
    return TradeResult(
        timestamp=now, pair=pair, action="CLOSE",
        stock_order_id=stock_order_id, stock_side=SIDE_SELL,
        stock_qty=qty, stock_price=stock_price,
        futures_order_id=futures_order_id, futures_side="buy",
        futures_qty=futures_qty, futures_price=futures_price,
        success=success, error=error,
    )


# ── Position helpers ─────────────────────────────────────────────────

def get_stock_positions() -> dict[str, float]:
    """Return a dict of {symbol: qty} for all Bit.com stock positions."""
    client = get_bitcom_client()
    positions = client.get_positions()
    return {p.symbol: p.qty for p in positions if p.qty > 0}


def get_futures_positions() -> dict[str, float]:
    """Return a dict of {symbol: qty} for all Binance futures positions.

    Negative qty = short position.
    """
    try:
        exchange = _get_futures_exchange()
        positions = exchange.fetch_positions()
        result = {}
        for p in positions:
            contracts = float(p.get("contracts", 0))
            side = p.get("side", "")
            if contracts > 0:
                qty = -contracts if side == "short" else contracts
                result[p["symbol"]] = qty
        return result
    except Exception:
        logger.exception("Failed to fetch Binance futures positions")
        return {}


def format_trade_result(tr: TradeResult) -> str:
    """Format a TradeResult for terminal display."""
    status = "✅ SUCCESS" if tr.success else f"❌ FAILED: {tr.error}"
    return (
        f"[{tr.timestamp:%H:%M:%S UTC}] {tr.action} {tr.pair.ticker}  "
        f"Stock: {tr.stock_side} {tr.stock_qty}sh @{tr.stock_price or 'MKT'} "
        f"(id={tr.stock_order_id or 'N/A'})  |  "
        f"Futures: {tr.futures_side} {tr.futures_qty:.4f} "
        f"@{tr.futures_price or 'MKT'} "
        f"(id={tr.futures_order_id or 'N/A'})  |  "
        f"{status}"
    )
