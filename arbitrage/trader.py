"""
trader.py – Execution module for funding-rate arbitrage.

**Maker-first execution strategy**:

Fee structure:
  • Binance TradFi futures:  maker = 0%,  taker = 0.04%
  • Bit.com US stocks:       maker/taker ≈ 0.01%

To minimise fees, we always:
  1. Place a **limit (maker) order on Binance** first and wait for fill.
  2. Once filled, immediately place a **market (taker) order on Bit.com**.

This gives us 0% on the Binance leg and ~0.01% on the stock leg,
instead of paying 0.04% as a Binance taker.

Handles:
  • OPEN  = Short futures on Binance (maker)  →  Buy stock on Bit.com (taker)
  • CLOSE = Buy-back futures on Binance (maker)  →  Sell stock on Bit.com (taker)

This module does NOT make autonomous trading decisions – it only executes
orders when explicitly called by the main loop or CLI.
"""

import logging
import time
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
    MAKER_ORDER_TIMEOUT,
    MAKER_POLL_INTERVAL,
)
from bitcom_client import SIDE_BUY, SIDE_SELL
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


def _place_futures_maker(
    symbol: str,
    side: str,
    qty: float,
    price: float,
    reduce_only: bool = False,
) -> dict:
    """Place a limit (maker) order on Binance perpetual futures.

    Always uses ``postOnly=True`` to guarantee maker execution (0% fee).
    """
    exchange = _get_futures_exchange()
    params: dict = {"postOnly": True}
    if reduce_only:
        params["reduceOnly"] = True

    order = exchange.create_order(
        symbol=symbol,
        type="limit",
        side=side,
        amount=qty,
        price=price,
        params=params,
    )
    logger.info(
        "Futures MAKER %s: %s qty=%.4f price=%.4f postOnly=True → id=%s",
        side.upper(), symbol, qty, price, order.get("id"),
    )
    return order


def _wait_for_fill(
    order_id: str,
    symbol: str,
    timeout: int = MAKER_ORDER_TIMEOUT,
    poll_interval: float = MAKER_POLL_INTERVAL,
) -> dict:
    """Poll Binance until a futures order is filled or timeout expires.

    Returns the final order dict.  Raises ``TimeoutError`` if the order
    is not fully filled within *timeout* seconds.  On timeout the order
    is cancelled automatically.
    """
    exchange = _get_futures_exchange()
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        order = exchange.fetch_order(order_id, symbol)
        status = order.get("status", "")
        filled = float(order.get("filled", 0))
        amount = float(order.get("amount", 0))

        logger.debug(
            "Order %s status=%s filled=%.4f/%.4f",
            order_id, status, filled, amount,
        )

        if status == "closed":
            logger.info("Order %s fully filled (%.4f)", order_id, filled)
            return order

        if status in ("canceled", "cancelled", "expired", "rejected"):
            raise RuntimeError(
                f"Order {order_id} ended with status={status} "
                f"(filled={filled}/{amount})"
            )

        time.sleep(poll_interval)

    # Timeout – cancel the unfilled order
    logger.warning("Order %s timed out after %ds – cancelling", order_id, timeout)
    try:
        exchange.cancel_order(order_id, symbol)
    except Exception:
        logger.exception("Failed to cancel timed-out order %s", order_id)

    # Re-fetch to see final state
    order = exchange.fetch_order(order_id, symbol)
    filled = float(order.get("filled", 0))
    if filled > 0:
        raise RuntimeError(
            f"Order {order_id} partially filled ({filled}) before timeout – "
            f"manual intervention needed!"
        )
    raise TimeoutError(
        f"Order {order_id} not filled within {timeout}s, cancelled."
    )


# ── Combined arbitrage trades ────────────────────────────────────────

def open_arb_position(
    pair: ArbPair,
    qty: int = 0,
    stock_price: Optional[float] = None,
    futures_price: Optional[float] = None,
) -> TradeResult:
    """Open a hedged position using maker-first execution.

    Execution order (to minimise fees):
      1. Place limit SELL (short) on Binance futures as **maker** (0% fee)
      2. Wait for Binance fill
      3. Place market BUY on Bit.com stock as **taker** (~0.01% fee)

    Args:
        pair: The arbitrage pair to trade.
        qty: Number of shares to buy (uses DEFAULT_TRADE_QTY if 0).
        stock_price: Ignored (stock leg always uses market order).
        futures_price: Limit price for the Binance maker order (required).

    Returns:
        A ``TradeResult`` describing both legs.
    """
    if qty <= 0:
        qty = DEFAULT_TRADE_QTY

    futures_qty = qty * pair.shares_per_contract
    now = datetime.now(timezone.utc)
    futures_order_id = ""
    stock_order_id = ""
    error = ""
    actual_futures_price: Optional[float] = futures_price

    # ── Leg 1: Binance maker short ───────────────────────────────────
    if futures_price is None:
        error = "futures_price is required for maker order"
        logger.error(error)
        return TradeResult(
            timestamp=now, pair=pair, action="OPEN",
            stock_order_id="", stock_side=SIDE_BUY,
            stock_qty=qty, stock_price=None,
            futures_order_id="", futures_side="sell",
            futures_qty=futures_qty, futures_price=None,
            success=False, error=error,
        )

    try:
        fut_order = _place_futures_maker(
            pair.futures_symbol, "sell", futures_qty, futures_price,
        )
        futures_order_id = fut_order.get("id", "")

        # Wait for fill
        filled_order = _wait_for_fill(futures_order_id, pair.futures_symbol)
        actual_futures_price = float(filled_order.get("average", futures_price))
        logger.info(
            "Binance maker SHORT filled: %s avg_price=%.4f",
            pair.futures_symbol, actual_futures_price,
        )
    except (TimeoutError, RuntimeError) as e:
        error = f"Binance maker leg failed: {e}"
        logger.error(error)
        return TradeResult(
            timestamp=now, pair=pair, action="OPEN",
            stock_order_id="", stock_side=SIDE_BUY,
            stock_qty=qty, stock_price=None,
            futures_order_id=futures_order_id, futures_side="sell",
            futures_qty=futures_qty, futures_price=futures_price,
            success=False, error=error,
        )
    except Exception as e:
        error = f"Binance maker leg failed: {e}"
        logger.exception("Failed to place/fill Binance maker order for %s", pair.futures_symbol)
        return TradeResult(
            timestamp=now, pair=pair, action="OPEN",
            stock_order_id="", stock_side=SIDE_BUY,
            stock_qty=qty, stock_price=None,
            futures_order_id=futures_order_id, futures_side="sell",
            futures_qty=futures_qty, futures_price=futures_price,
            success=False, error=error,
        )

    # ── Leg 2: Bit.com stock taker buy ───────────────────────────────
    try:
        client = get_bitcom_client()
        stock_order = client.place_order(
            symbol=pair.stock_symbol,
            side=SIDE_BUY,
            qty=qty,
            price=None,           # market order (taker)
            order_type="MO",      # market order
            remark=f"arb-open-{pair.ticker}",
        )
        stock_order_id = stock_order.order_id
        logger.info(
            "Bit.com taker BUY placed: %s qty=%d → %s",
            pair.stock_symbol, qty, stock_order_id,
        )
    except Exception as e:
        error = (
            f"Stock taker leg failed (Binance short {futures_order_id} IS LIVE!): {e}"
        )
        logger.exception(
            "Failed to buy stock %s – BINANCE SHORT %s IS LIVE, manual intervention needed!",
            pair.stock_symbol, futures_order_id,
        )

    success = bool(stock_order_id and futures_order_id and not error)
    return TradeResult(
        timestamp=now, pair=pair, action="OPEN",
        stock_order_id=stock_order_id, stock_side=SIDE_BUY,
        stock_qty=qty, stock_price=None,
        futures_order_id=futures_order_id, futures_side="sell",
        futures_qty=futures_qty, futures_price=actual_futures_price,
        success=success, error=error,
    )


def close_arb_position(
    pair: ArbPair,
    qty: int = 0,
    stock_price: Optional[float] = None,
    futures_price: Optional[float] = None,
) -> TradeResult:
    """Close a hedged position using maker-first execution.

    Execution order (to minimise fees):
      1. Place limit BUY on Binance futures as **maker** (0% fee, reduceOnly)
      2. Wait for Binance fill
      3. Place market SELL on Bit.com stock as **taker** (~0.01% fee)

    Args:
        pair: The arbitrage pair to close.
        qty: Number of shares to sell (uses DEFAULT_TRADE_QTY if 0).
        stock_price: Ignored (stock leg always uses market order).
        futures_price: Limit price for the Binance maker buy-back (required).

    Returns:
        A ``TradeResult`` describing both legs.
    """
    if qty <= 0:
        qty = DEFAULT_TRADE_QTY

    futures_qty = qty * pair.shares_per_contract
    now = datetime.now(timezone.utc)
    futures_order_id = ""
    stock_order_id = ""
    error = ""
    actual_futures_price: Optional[float] = futures_price

    # ── Leg 1: Binance maker buy-back ────────────────────────────────
    if futures_price is None:
        error = "futures_price is required for maker order"
        logger.error(error)
        return TradeResult(
            timestamp=now, pair=pair, action="CLOSE",
            stock_order_id="", stock_side=SIDE_SELL,
            stock_qty=qty, stock_price=None,
            futures_order_id="", futures_side="buy",
            futures_qty=futures_qty, futures_price=None,
            success=False, error=error,
        )

    try:
        fut_order = _place_futures_maker(
            pair.futures_symbol, "buy", futures_qty, futures_price,
            reduce_only=True,
        )
        futures_order_id = fut_order.get("id", "")

        # Wait for fill
        filled_order = _wait_for_fill(futures_order_id, pair.futures_symbol)
        actual_futures_price = float(filled_order.get("average", futures_price))
        logger.info(
            "Binance maker BUY-BACK filled: %s avg_price=%.4f",
            pair.futures_symbol, actual_futures_price,
        )
    except (TimeoutError, RuntimeError) as e:
        error = f"Binance maker close leg failed: {e}"
        logger.error(error)
        return TradeResult(
            timestamp=now, pair=pair, action="CLOSE",
            stock_order_id="", stock_side=SIDE_SELL,
            stock_qty=qty, stock_price=None,
            futures_order_id=futures_order_id, futures_side="buy",
            futures_qty=futures_qty, futures_price=futures_price,
            success=False, error=error,
        )
    except Exception as e:
        error = f"Binance maker close leg failed: {e}"
        logger.exception("Failed to place/fill Binance maker buy-back for %s", pair.futures_symbol)
        return TradeResult(
            timestamp=now, pair=pair, action="CLOSE",
            stock_order_id="", stock_side=SIDE_SELL,
            stock_qty=qty, stock_price=None,
            futures_order_id=futures_order_id, futures_side="buy",
            futures_qty=futures_qty, futures_price=futures_price,
            success=False, error=error,
        )

    # ── Leg 2: Bit.com stock taker sell ──────────────────────────────
    try:
        client = get_bitcom_client()
        stock_order = client.place_order(
            symbol=pair.stock_symbol,
            side=SIDE_SELL,
            qty=qty,
            price=None,           # market order (taker)
            order_type="MO",      # market order
            remark=f"arb-close-{pair.ticker}",
        )
        stock_order_id = stock_order.order_id
        logger.info(
            "Bit.com taker SELL placed: %s qty=%d → %s",
            pair.stock_symbol, qty, stock_order_id,
        )
    except Exception as e:
        error = (
            f"Stock taker sell failed (Binance buy-back {futures_order_id} IS DONE!): {e}"
        )
        logger.exception(
            "Failed to sell stock %s – BINANCE BUY-BACK %s IS DONE, manual intervention needed!",
            pair.stock_symbol, futures_order_id,
        )

    success = bool(stock_order_id and futures_order_id and not error)
    return TradeResult(
        timestamp=now, pair=pair, action="CLOSE",
        stock_order_id=stock_order_id, stock_side=SIDE_SELL,
        stock_qty=qty, stock_price=None,
        futures_order_id=futures_order_id, futures_side="buy",
        futures_qty=futures_qty, futures_price=actual_futures_price,
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
    stock_price_str = f"@{tr.stock_price:.2f}" if tr.stock_price else "@MKT"
    futures_price_str = f"@{tr.futures_price:.4f}" if tr.futures_price else "@N/A"
    return (
        f"[{tr.timestamp:%H:%M:%S UTC}] {tr.action} {tr.pair.ticker}  "
        f"① Futures(maker): {tr.futures_side} {tr.futures_qty:.4f} "
        f"{futures_price_str} "
        f"(id={tr.futures_order_id or 'N/A'})  →  "
        f"② Stock(taker): {tr.stock_side} {tr.stock_qty}sh {stock_price_str} "
        f"(id={tr.stock_order_id or 'N/A'})  |  "
        f"{status}"
    )
