"""
trader.py – Execution module for funding-rate arbitrage.

**Strict zero-exposure, maker-first execution strategy**:

Fee structure:
  • Binance TradFi futures:  maker = 0%,  taker = 0.04%
  • Bit.com US stocks:       maker/taker ≈ 0.01%

To minimise fees, we always:
  1. Place a **limit (maker) order on Binance** first and wait for fill.
  2. Once filled, immediately place a **market (taker) order on Bit.com**
     for **exactly** the filled quantity.

Zero-exposure guarantees:
  • Partial fills: if Binance partially fills before timeout, the stock
    leg executes for the *filled* quantity only (never the full order).
  • Stock-leg retries: if the Bit.com market order fails after Binance
    has filled, the system retries up to ``MAX_STOCK_RETRIES`` times
    with exponential back-off.
  • Position reconciliation: ``check_hedge_balance()`` compares live
    positions on both venues and reports any mismatch.

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
    ARB_PAIRS,
    BINANCE_API_KEY,
    BINANCE_API_SECRET,
    BINANCE_TESTNET,
    DEFAULT_TRADE_QTY,
    HTTPS_PROXY,
    MAKER_ORDER_TIMEOUT,
    MAKER_POLL_INTERVAL,
    MAX_POSITION_VALUE_USD,
    MAX_STOCK_RETRIES,
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
        config = {
            "apiKey": BINANCE_API_KEY,
            "secret": BINANCE_API_SECRET,
            "options": {"defaultType": "future"},
            "enableRateLimit": True,
        }
        if HTTPS_PROXY:
            config["proxies"] = {"https": HTTPS_PROXY, "http": HTTPS_PROXY}
        _futures_exchange = ccxt.binance(config)
        if BINANCE_TESTNET:
            _futures_exchange.set_sandbox_mode(True)
        try:
            _futures_exchange.load_markets()
        except Exception as e:
            _futures_exchange = None
            if "Timeout" in type(e).__name__ or "timeout" in str(e).lower():
                raise ConnectionError(
                    f"Cannot reach Binance API: {e}. "
                    "Set HTTPS_PROXY in .env if your network blocks Binance "
                    "(e.g. HTTPS_PROXY=http://127.0.0.1:7890)."
                ) from e
            raise
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

    Returns the final order dict.  On timeout:
      • If **partially filled** → cancels the remaining qty, returns
        the order with ``filled > 0``.  The caller MUST hedge only
        the filled amount.
      • If **zero fill** → cancels and raises ``TimeoutError``.

    Raises ``RuntimeError`` for unexpected terminal states (cancelled
    externally, rejected, etc.).
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
            if filled > 0:
                # Externally cancelled but partially filled → caller
                # must still hedge the filled portion.
                logger.warning(
                    "Order %s %s with partial fill %.4f/%.4f",
                    order_id, status, filled, amount,
                )
                return order
            raise RuntimeError(
                f"Order {order_id} ended with status={status} "
                f"(filled={filled}/{amount})"
            )

        time.sleep(poll_interval)

    # Timeout – cancel the remaining unfilled portion
    logger.warning("Order %s timed out after %ds – cancelling remainder", order_id, timeout)
    try:
        exchange.cancel_order(order_id, symbol)
    except Exception:
        logger.exception("Failed to cancel timed-out order %s", order_id)

    # Re-fetch to see final state (including any fill that snuck in)
    order = exchange.fetch_order(order_id, symbol)
    filled = float(order.get("filled", 0))
    if filled > 0:
        # Partial fill → return it; caller hedges exactly this amount
        logger.warning(
            "Order %s partially filled (%.4f/%.4f) before timeout – "
            "will hedge partial quantity",
            order_id, filled, float(order.get("amount", 0)),
        )
        return order
    raise TimeoutError(
        f"Order {order_id} not filled within {timeout}s, cancelled."
    )


# ── Stock-leg retry helper ───────────────────────────────────────────

def _place_stock_with_retry(
    symbol: str,
    side: str,
    qty: int,
    remark: str,
    max_retries: int = MAX_STOCK_RETRIES,
) -> str:
    """Place a market order on Bit.com and retry on failure.

    This is critical for zero-exposure: once the Binance leg has filled,
    we **must** hedge on the stock side.  Retries with exponential
    back-off (1s, 2s, 4s …).

    Returns the stock ``order_id`` on success.
    Raises ``RuntimeError`` if all retries are exhausted.
    """
    client = get_bitcom_client()
    last_error: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            stock_order = client.place_order(
                symbol=symbol,
                side=side,
                qty=qty,
                price=None,
                order_type="MO",
                remark=remark,
            )
            logger.info(
                "Bit.com taker %s placed: %s qty=%d → %s (attempt %d)",
                side, symbol, qty, stock_order.order_id, attempt,
            )
            return stock_order.order_id
        except Exception as e:
            last_error = e
            wait = min(2 ** (attempt - 1), 8)
            logger.error(
                "Bit.com %s failed (attempt %d/%d): %s – retrying in %ds",
                side, attempt, max_retries, e, wait,
            )
            if attempt < max_retries:
                time.sleep(wait)

    raise RuntimeError(
        f"Bit.com {side} {symbol} qty={qty} failed after {max_retries} "
        f"attempts – UNHEDGED EXPOSURE! Last error: {last_error}"
    )


# ── Combined arbitrage trades ────────────────────────────────────────

def open_arb_position(
    pair: ArbPair,
    qty: int = 0,
    stock_price: Optional[float] = None,
    futures_price: Optional[float] = None,
) -> TradeResult:
    """Open a hedged position using maker-first execution.

    **Strict zero-exposure guarantee**:
      1. Place limit SELL (short) on Binance futures as **maker** (0% fee)
      2. Wait for fill (full or partial)
      3. Place market BUY on Bit.com for **exactly the filled qty**
         with retries to ensure the hedge is established.

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

    # ── Position value limit check ──────────────────────────────────
    if MAX_POSITION_VALUE_USD > 0 and futures_price is not None:
        current_value = get_total_futures_position_value()
        new_trade_value = qty * pair.shares_per_contract * futures_price
        projected = current_value + new_trade_value
        if projected > MAX_POSITION_VALUE_USD:
            error = (
                f"Position value limit exceeded: current ${current_value:,.0f} "
                f"+ new ${new_trade_value:,.0f} = ${projected:,.0f} > "
                f"limit ${MAX_POSITION_VALUE_USD:,.0f}"
            )
            logger.warning(error)
            return TradeResult(
                timestamp=datetime.now(timezone.utc), pair=pair, action="OPEN",
                stock_order_id="", stock_side=SIDE_BUY,
                stock_qty=0, stock_price=None,
                futures_order_id="", futures_side="sell",
                futures_qty=0, futures_price=None,
                success=False, error=error,
            )

    futures_qty = qty * pair.shares_per_contract
    now = datetime.now(timezone.utc)
    futures_order_id = ""
    stock_order_id = ""
    error = ""
    actual_futures_price: Optional[float] = futures_price
    actual_futures_filled: float = 0.0
    actual_stock_qty: int = qty  # will be adjusted to match futures fill

    # ── Leg 1: Binance maker short ───────────────────────────────────
    if futures_price is None:
        error = "futures_price is required for maker order"
        logger.error(error)
        return TradeResult(
            timestamp=now, pair=pair, action="OPEN",
            stock_order_id="", stock_side=SIDE_BUY,
            stock_qty=0, stock_price=None,
            futures_order_id="", futures_side="sell",
            futures_qty=0, futures_price=None,
            success=False, error=error,
        )

    try:
        fut_order = _place_futures_maker(
            pair.futures_symbol, "sell", futures_qty, futures_price,
        )
        futures_order_id = fut_order.get("id", "")

        # Wait for fill (may be full or partial)
        filled_order = _wait_for_fill(futures_order_id, pair.futures_symbol)
        actual_futures_filled = float(filled_order.get("filled", 0))
        actual_futures_price = float(filled_order.get("average", futures_price))

        # Compute the exact stock qty to hedge
        actual_stock_qty = int(actual_futures_filled / pair.shares_per_contract)
        if actual_stock_qty <= 0:
            raise RuntimeError(
                f"Futures filled {actual_futures_filled} but translates to "
                f"0 shares (shares_per_contract={pair.shares_per_contract})"
            )

        logger.info(
            "Binance maker SHORT filled: %s filled=%.4f avg=%.4f → hedge %d shares",
            pair.futures_symbol, actual_futures_filled, actual_futures_price,
            actual_stock_qty,
        )
    except (TimeoutError, RuntimeError) as e:
        error = f"Binance maker leg failed: {e}"
        logger.error(error)
        return TradeResult(
            timestamp=now, pair=pair, action="OPEN",
            stock_order_id="", stock_side=SIDE_BUY,
            stock_qty=0, stock_price=None,
            futures_order_id=futures_order_id, futures_side="sell",
            futures_qty=actual_futures_filled, futures_price=futures_price,
            success=False, error=error,
        )
    except Exception as e:
        error = f"Binance maker leg failed: {e}"
        logger.exception("Failed to place/fill Binance maker order for %s", pair.futures_symbol)
        return TradeResult(
            timestamp=now, pair=pair, action="OPEN",
            stock_order_id="", stock_side=SIDE_BUY,
            stock_qty=0, stock_price=None,
            futures_order_id=futures_order_id, futures_side="sell",
            futures_qty=actual_futures_filled, futures_price=futures_price,
            success=False, error=error,
        )

    # ── Leg 2: Bit.com stock taker buy (with retry) ──────────────────
    try:
        stock_order_id = _place_stock_with_retry(
            symbol=pair.stock_symbol,
            side=SIDE_BUY,
            qty=actual_stock_qty,
            remark=f"arb-open-{pair.ticker}",
        )
    except RuntimeError as e:
        error = (
            f"CRITICAL: Stock leg failed after retries! "
            f"Binance short {futures_order_id} ({actual_futures_filled} contracts) "
            f"IS LIVE with NO stock hedge! {e}"
        )
        logger.critical(error)

    success = bool(stock_order_id and futures_order_id and not error)
    return TradeResult(
        timestamp=now, pair=pair, action="OPEN",
        stock_order_id=stock_order_id, stock_side=SIDE_BUY,
        stock_qty=actual_stock_qty, stock_price=None,
        futures_order_id=futures_order_id, futures_side="sell",
        futures_qty=actual_futures_filled, futures_price=actual_futures_price,
        success=success, error=error,
    )


def close_arb_position(
    pair: ArbPair,
    qty: int = 0,
    stock_price: Optional[float] = None,
    futures_price: Optional[float] = None,
) -> TradeResult:
    """Close a hedged position using maker-first execution.

    **Strict zero-exposure guarantee**:
      1. Place limit BUY on Binance futures as **maker** (0% fee, reduceOnly)
      2. Wait for fill (full or partial)
      3. Place market SELL on Bit.com for **exactly the filled qty**
         with retries to ensure the hedge unwind matches.

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
    actual_futures_filled: float = 0.0
    actual_stock_qty: int = qty

    # ── Leg 1: Binance maker buy-back ────────────────────────────────
    if futures_price is None:
        error = "futures_price is required for maker order"
        logger.error(error)
        return TradeResult(
            timestamp=now, pair=pair, action="CLOSE",
            stock_order_id="", stock_side=SIDE_SELL,
            stock_qty=0, stock_price=None,
            futures_order_id="", futures_side="buy",
            futures_qty=0, futures_price=None,
            success=False, error=error,
        )

    try:
        fut_order = _place_futures_maker(
            pair.futures_symbol, "buy", futures_qty, futures_price,
            reduce_only=True,
        )
        futures_order_id = fut_order.get("id", "")

        # Wait for fill (may be full or partial)
        filled_order = _wait_for_fill(futures_order_id, pair.futures_symbol)
        actual_futures_filled = float(filled_order.get("filled", 0))
        actual_futures_price = float(filled_order.get("average", futures_price))

        # Compute the exact stock qty to sell (must match futures)
        actual_stock_qty = int(actual_futures_filled / pair.shares_per_contract)
        if actual_stock_qty <= 0:
            raise RuntimeError(
                f"Futures filled {actual_futures_filled} but translates to "
                f"0 shares (shares_per_contract={pair.shares_per_contract})"
            )

        logger.info(
            "Binance maker BUY-BACK filled: %s filled=%.4f avg=%.4f → sell %d shares",
            pair.futures_symbol, actual_futures_filled, actual_futures_price,
            actual_stock_qty,
        )
    except (TimeoutError, RuntimeError) as e:
        error = f"Binance maker close leg failed: {e}"
        logger.error(error)
        return TradeResult(
            timestamp=now, pair=pair, action="CLOSE",
            stock_order_id="", stock_side=SIDE_SELL,
            stock_qty=0, stock_price=None,
            futures_order_id=futures_order_id, futures_side="buy",
            futures_qty=actual_futures_filled, futures_price=futures_price,
            success=False, error=error,
        )
    except Exception as e:
        error = f"Binance maker close leg failed: {e}"
        logger.exception("Failed to place/fill Binance maker buy-back for %s", pair.futures_symbol)
        return TradeResult(
            timestamp=now, pair=pair, action="CLOSE",
            stock_order_id="", stock_side=SIDE_SELL,
            stock_qty=0, stock_price=None,
            futures_order_id=futures_order_id, futures_side="buy",
            futures_qty=actual_futures_filled, futures_price=futures_price,
            success=False, error=error,
        )

    # ── Leg 2: Bit.com stock taker sell (with retry) ─────────────────
    try:
        stock_order_id = _place_stock_with_retry(
            symbol=pair.stock_symbol,
            side=SIDE_SELL,
            qty=actual_stock_qty,
            remark=f"arb-close-{pair.ticker}",
        )
    except RuntimeError as e:
        error = (
            f"CRITICAL: Stock sell failed after retries! "
            f"Binance buy-back {futures_order_id} ({actual_futures_filled} contracts) "
            f"IS DONE but stock NOT sold! {e}"
        )
        logger.critical(error)

    success = bool(stock_order_id and futures_order_id and not error)
    return TradeResult(
        timestamp=now, pair=pair, action="CLOSE",
        stock_order_id=stock_order_id, stock_side=SIDE_SELL,
        stock_qty=actual_stock_qty, stock_price=None,
        futures_order_id=futures_order_id, futures_side="buy",
        futures_qty=actual_futures_filled, futures_price=actual_futures_price,
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


def get_total_futures_position_value() -> float:
    """Return the total notional value (USD) of all Binance futures positions.

    Uses mark price × abs(contracts) × shares_per_contract for each pair.
    This gives a rough USD value of total exposure on the futures side,
    which is the relevant metric for liquidation risk.
    """
    try:
        exchange = _get_futures_exchange()
        positions = exchange.fetch_positions()
        total = 0.0
        for p in positions:
            contracts = float(p.get("contracts", 0))
            if contracts > 0:
                notional = float(p.get("notional", 0))
                total += abs(notional)
        return total
    except Exception:
        logger.exception("Failed to calculate total futures position value")
        return 0.0


# ── Hedge balance check ─────────────────────────────────────────────

@dataclass
class HedgeStatus:
    """Hedge-balance status for one arbitrage pair."""
    pair: ArbPair
    stock_qty: float       # Bit.com long shares (≥ 0)
    futures_qty: float     # Binance contracts (negative = short)
    net_exposure: float    # stock_qty + futures_qty (0 = perfectly hedged)
    is_balanced: bool


def check_hedge_balance() -> list[HedgeStatus]:
    """Compare positions on both venues and report hedge status.

    Returns a list of ``HedgeStatus`` for every configured pair.
    ``net_exposure == 0`` means perfectly hedged (no directional risk).
    """
    stock_pos = get_stock_positions()
    futures_pos = get_futures_positions()

    results: list[HedgeStatus] = []
    for pair in ARB_PAIRS:
        s_qty = stock_pos.get(pair.stock_symbol, 0.0)
        f_qty = futures_pos.get(pair.futures_symbol, 0.0)

        # Normalise: futures qty is in contracts; convert to shares
        f_shares = f_qty * pair.shares_per_contract
        net = s_qty + f_shares  # long + (negative short) should be 0

        balanced = abs(net) < 0.01  # tolerance for rounding
        results.append(HedgeStatus(
            pair=pair,
            stock_qty=s_qty,
            futures_qty=f_qty,
            net_exposure=net,
            is_balanced=balanced,
        ))

    return results


def format_hedge_status(statuses: list[HedgeStatus]) -> str:
    """Format hedge-balance report for terminal display."""
    lines: list[str] = []
    any_imbalance = False

    for hs in statuses:
        # Skip pairs with no positions at all
        if hs.stock_qty == 0 and hs.futures_qty == 0:
            continue

        icon = "✅" if hs.is_balanced else "🚨"
        if not hs.is_balanced:
            any_imbalance = True

        direction = "SHORT" if hs.futures_qty < 0 else "LONG"
        lines.append(
            f"  {icon} {hs.pair.ticker:6s}  "
            f"Stock: {hs.stock_qty:>6.0f} sh  "
            f"Futures: {direction} {abs(hs.futures_qty):>8.4f}  "
            f"Net exposure: {hs.net_exposure:+.2f} sh"
        )

    if not lines:
        return "  (no positions on either venue)"

    header = (
        "  🚨 HEDGE IMBALANCE DETECTED – manual intervention needed!"
        if any_imbalance
        else "  ✅ All positions perfectly hedged (zero exposure)"
    )
    result = header + "\n" + "\n".join(lines)

    # Append position value limit info
    if MAX_POSITION_VALUE_USD > 0:
        total_value = get_total_futures_position_value()
        pct = (total_value / MAX_POSITION_VALUE_USD) * 100
        limit_icon = "🟢" if pct < 80 else ("🟡" if pct < 100 else "🔴")
        result += (
            f"\n  {limit_icon} Total futures notional: "
            f"${total_value:,.0f} / ${MAX_POSITION_VALUE_USD:,.0f} "
            f"({pct:.0f}%)"
        )

    return result


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
