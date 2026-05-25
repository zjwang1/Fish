"""
bitcom_client.py – Bit.com (Matrixport) Stock API client.

Provides authenticated access to the Bit.com Stock Trading API at
``https://mapi.matrixport.com/stock/v1/...``

Features:
  • HMAC-SHA256 request signing
  • Place / cancel orders
  • Query open orders & order history
  • Get positions
  • Get real-time stock quotes

Reference: https://www.bit.com/docs/en-us/stock.html#stock-api
"""

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────

BASE_URL = "https://mapi.matrixport.com"

# Order sides
SIDE_BUY = "Buy"
SIDE_SELL = "Sell"

# Order types
ORDER_TYPE_LIMIT = "LO"       # Limit order
ORDER_TYPE_MARKET = "MO"      # Market order (if supported)
ORDER_TYPE_ALO = "ALO"        # At-Limit-Or-better

# Time in force
TIF_DAY = "Day"
TIF_GTC = "GTC"               # Good-till-cancel
TIF_GTD = "GTD"               # Good-till-date


# ── Data containers ──────────────────────────────────────────────────

@dataclass
class StockOrder:
    """Represents a stock order response."""
    order_id: str
    symbol: str
    side: str
    qty: str
    price: Optional[str]
    order_type: str
    status: str = ""
    filled_qty: str = "0"
    avg_price: str = "0"


@dataclass
class StockPosition:
    """Represents a stock position."""
    symbol: str
    qty: float
    avg_cost: float
    market_value: float
    unrealised_pnl: float


@dataclass
class StockQuote:
    """Real-time stock quote."""
    symbol: str
    last_price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[float] = None
    change_pct: Optional[float] = None


# ── Client ───────────────────────────────────────────────────────────

class BitcomStockClient:
    """Authenticated client for the Bit.com Stock Trading API.

    Usage::

        client = BitcomStockClient(access_key="...", secret_key="...")
        quote = client.get_quote("AAPL.US")
        order = client.place_order("AAPL.US", "Buy", qty=10, price=150.50)
        client.cancel_order(order.order_id)
    """

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        base_url: str = BASE_URL,
    ) -> None:
        self.access_key = access_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    # ── Authentication ───────────────────────────────────────────────

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """Create HMAC-SHA256 signature.

        Sign string = timestamp + access_key + METHOD + path [+ body]
        """
        sign_str = f"{timestamp}{self.access_key}{method.upper()}{path}{body}"
        return hmac.new(
            self.secret_key.encode("utf-8"),
            sign_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _auth_headers(self, method: str, path: str, body: str = "") -> dict[str, str]:
        """Build authentication headers for a request."""
        timestamp = str(int(time.time() * 1000))
        signature = self._sign(timestamp, method, path, body)
        return {
            "X-MatrixPort-Access-Key": self.access_key,
            "X-MatrixPort-Request-Timestamp": timestamp,
            "X-MatrixPort-Signature": signature,
        }

    # ── Low-level request helpers ────────────────────────────────────

    def _get(self, path: str, params: Optional[dict] = None) -> dict[str, Any]:
        """Authenticated GET request."""
        if params:
            query = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v is not None)
            full_path = f"{path}?{query}" if query else path
        else:
            full_path = path

        headers = self._auth_headers("GET", full_path)
        url = f"{self.base_url}{full_path}"

        logger.debug("GET %s", url)
        resp = self._session.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise BitcomApiError(data.get("code", -1), data.get("message", "Unknown error"))
        return data

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """Authenticated POST request."""
        body_str = json.dumps(body, separators=(",", ":"))
        headers = self._auth_headers("POST", path, body_str)
        url = f"{self.base_url}{path}"

        logger.debug("POST %s  body=%s", url, body_str)
        resp = self._session.post(url, headers=headers, data=body_str, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise BitcomApiError(data.get("code", -1), data.get("message", "Unknown error"))
        return data

    # ── Market data ──────────────────────────────────────────────────

    def get_quote(self, symbol: str) -> Optional[StockQuote]:
        """Get real-time quote for a stock.

        *symbol* should be in Bit.com format, e.g. ``"AAPL.US"``.
        """
        try:
            resp = self._get("/stock/v1/quote", {"symbol": symbol})
            d = resp.get("data", {})
            return StockQuote(
                symbol=symbol,
                last_price=float(d.get("last_price", 0)),
                bid=_safe_float(d.get("bid")),
                ask=_safe_float(d.get("ask")),
                volume=_safe_float(d.get("volume")),
                change_pct=_safe_float(d.get("change_pct")),
            )
        except Exception:
            logger.exception("Failed to get quote for %s", symbol)
            return None

    def get_stock_list(self) -> list[dict[str, Any]]:
        """Get list of available stocks."""
        try:
            resp = self._get("/stock/v1/stock_list")
            return resp.get("data", [])
        except Exception:
            logger.exception("Failed to get stock list")
            return []

    # ── Order management ─────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: Optional[float] = None,
        order_type: str = ORDER_TYPE_LIMIT,
        time_in_force: str = TIF_DAY,
        outside_rth: bool = False,
        remark: str = "",
    ) -> StockOrder:
        """Place a stock order.

        Args:
            symbol: e.g. ``"MU.US"``
            side: ``"Buy"`` or ``"Sell"``
            qty: Number of shares (positive integer)
            price: Limit price (required for limit orders)
            order_type: ``"LO"`` (limit), ``"MO"`` (market)
            time_in_force: ``"Day"``, ``"GTC"``, ``"GTD"``
            outside_rth: Allow trading outside regular hours
            remark: Optional note

        Returns:
            A ``StockOrder`` with the ``order_id`` populated.
        """
        body: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "qty": str(qty),
            "order_type": order_type,
        }
        if price is not None:
            body["price"] = f"{price:.2f}"
        if time_in_force != TIF_DAY:
            body["time_in_force"] = time_in_force
        if outside_rth:
            body["outside_rth"] = "true"
        if remark:
            body["remark"] = remark

        resp = self._post("/stock/v1/place_order", body)
        data = resp.get("data", {})

        logger.info(
            "Order placed: %s %s %s qty=%d price=%s → order_id=%s",
            side, symbol, order_type, qty, price, data.get("order_id"),
        )
        return StockOrder(
            order_id=data.get("order_id", ""),
            symbol=symbol,
            side=side,
            qty=str(qty),
            price=body.get("price"),
            order_type=order_type,
        )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order by order_id."""
        try:
            self._post("/stock/v1/cancel_order", {"order_id": order_id})
            logger.info("Order cancelled: %s", order_id)
            return True
        except Exception:
            logger.exception("Failed to cancel order %s", order_id)
            return False

    def get_open_orders(self, symbol: Optional[str] = None) -> list[StockOrder]:
        """Get all open (active) orders."""
        try:
            params = {}
            if symbol:
                params["symbol"] = symbol
            resp = self._get("/stock/v1/open_orders", params or None)
            orders = []
            for d in resp.get("data", []):
                orders.append(StockOrder(
                    order_id=d.get("order_id", ""),
                    symbol=d.get("symbol", ""),
                    side=d.get("side", ""),
                    qty=d.get("qty", "0"),
                    price=d.get("price"),
                    order_type=d.get("order_type", ""),
                    status=d.get("status", ""),
                    filled_qty=d.get("filled_qty", "0"),
                    avg_price=d.get("avg_price", "0"),
                ))
            return orders
        except Exception:
            logger.exception("Failed to get open orders")
            return []

    def get_order_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 50,
    ) -> list[StockOrder]:
        """Get historical (filled/cancelled) orders."""
        try:
            params: dict[str, Any] = {"limit": str(limit)}
            if symbol:
                params["symbol"] = symbol
            resp = self._get("/stock/v1/order_history", params)
            orders = []
            for d in resp.get("data", []):
                orders.append(StockOrder(
                    order_id=d.get("order_id", ""),
                    symbol=d.get("symbol", ""),
                    side=d.get("side", ""),
                    qty=d.get("qty", "0"),
                    price=d.get("price"),
                    order_type=d.get("order_type", ""),
                    status=d.get("status", ""),
                    filled_qty=d.get("filled_qty", "0"),
                    avg_price=d.get("avg_price", "0"),
                ))
            return orders
        except Exception:
            logger.exception("Failed to get order history")
            return []

    # ── Position management ──────────────────────────────────────────

    def get_positions(self, symbol: Optional[str] = None) -> list[StockPosition]:
        """Get current stock positions."""
        try:
            params = {}
            if symbol:
                params["symbol"] = symbol
            resp = self._get("/stock/v1/positions", params or None)
            positions = []
            for d in resp.get("data", []):
                positions.append(StockPosition(
                    symbol=d.get("symbol", ""),
                    qty=float(d.get("qty", 0)),
                    avg_cost=float(d.get("avg_cost", 0)),
                    market_value=float(d.get("market_value", 0)),
                    unrealised_pnl=float(d.get("unrealised_pnl", 0)),
                ))
            return positions
        except Exception:
            logger.exception("Failed to get positions")
            return []

    # ── Account ──────────────────────────────────────────────────────

    def get_account_info(self) -> dict[str, Any]:
        """Get account summary (balance, buying power, etc.)."""
        try:
            resp = self._get("/stock/v1/account")
            return resp.get("data", {})
        except Exception:
            logger.exception("Failed to get account info")
            return {}


# ── Exceptions ───────────────────────────────────────────────────────

class BitcomApiError(Exception):
    """Raised when the Bit.com API returns a non-zero code."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"BitcomApiError({code}): {message}")


# ── Utilities ────────────────────────────────────────────────────────

def _safe_float(val: Any) -> Optional[float]:
    """Convert a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
