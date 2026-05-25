"""
binance_client.py – Lightweight Binance USDT-M Futures REST client.

Uses only ``requests`` + HMAC-SHA256 signing.  Replaces the ``ccxt``
dependency for all Binance operations in this project.

Public endpoints (no auth):
  • ticker price
  • funding rate (current & history)

Signed endpoints:
  • place / fetch / cancel orders
  • fetch account positions
"""

import hashlib
import hmac
import logging
import time
from typing import Any, Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

# ── Defaults ─────────────────────────────────────────────────────────

_LIVE_BASE = "https://fapi.binance.com"
_TESTNET_BASE = "https://testnet.binancefuture.com"

_RECV_WINDOW = 5000
_TIMEOUT = 15  # seconds per HTTP request


def _to_raw_symbol(unified: str) -> str:
    """Convert a unified symbol like ``MU/USDT:USDT`` to ``MUUSDT``.

    Also accepts raw symbols (``MUUSDT``) as a no-op pass-through.
    """
    if "/" in unified:
        base = unified.split(":")[0]  # 'MU/USDT'
        return base.replace("/", "")  # 'MUUSDT'
    return unified


class BinanceFuturesClient:
    """Minimal Binance USDT-M Futures REST client.

    Parameters
    ----------
    api_key : str
        Binance API key (may be empty for public-only usage).
    api_secret : str
        Binance API secret.
    testnet : bool
        If *True*, use ``testnet.binancefuture.com``.
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        testnet: bool = False,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._base = _TESTNET_BASE if testnet else _LIVE_BASE
        self._session = requests.Session()
        if api_key:
            self._session.headers["X-MBX-APIKEY"] = api_key

    # ── Low-level helpers ────────────────────────────────────────────

    def _sign(self, params: dict) -> dict:
        """Add ``timestamp``, ``recvWindow`` and ``signature`` to *params*."""
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = _RECV_WINDOW
        qs = urlencode(params)
        sig = hmac.new(
            self._api_secret.encode(), qs.encode(), hashlib.sha256,
        ).hexdigest()
        params["signature"] = sig
        return params

    def _public_get(self, path: str, params: Optional[dict] = None) -> Any:
        """Unsigned GET request."""
        url = f"{self._base}{path}"
        resp = self._session.get(url, params=params or {}, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def _signed_get(self, path: str, params: Optional[dict] = None) -> Any:
        """Signed GET request (requires API key + secret)."""
        url = f"{self._base}{path}"
        resp = self._session.get(
            url, params=self._sign(params or {}), timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    def _signed_post(self, path: str, params: Optional[dict] = None) -> Any:
        """Signed POST request."""
        url = f"{self._base}{path}"
        resp = self._session.post(
            url, params=self._sign(params or {}), timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    def _signed_delete(self, path: str, params: Optional[dict] = None) -> Any:
        """Signed DELETE request."""
        url = f"{self._base}{path}"
        resp = self._session.delete(
            url, params=self._sign(params or {}), timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Public market data ───────────────────────────────────────────

    def get_ticker_price(self, symbol: str) -> Optional[float]:
        """Return the latest price for a futures symbol.

        *symbol* can be unified (``MU/USDT:USDT``) or raw (``MUUSDT``).
        """
        raw = _to_raw_symbol(symbol)
        data = self._public_get("/fapi/v1/ticker/price", {"symbol": raw})
        price = float(data.get("price", 0))
        return price if price > 0 else None

    def get_mark_price(self, symbol: str) -> dict:
        """Return mark price, index price and current funding rate.

        Returns a dict with keys: ``markPrice``, ``indexPrice``,
        ``lastFundingRate``, ``nextFundingTime``, ``time``.
        """
        raw = _to_raw_symbol(symbol)
        return self._public_get("/fapi/v1/premiumIndex", {"symbol": raw})

    def get_funding_rate_history(
        self,
        symbol: str,
        *,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Fetch historical funding rates.

        ``GET /fapi/v1/fundingRate``  (public, no auth).
        """
        raw = _to_raw_symbol(symbol)
        params: dict[str, Any] = {"symbol": raw, "limit": limit}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        return self._public_get("/fapi/v1/fundingRate", params)

    # ── Signed order management ──────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        *,
        order_type: str = "LIMIT",
        price: Optional[float] = None,
        time_in_force: str = "GTC",
        post_only: bool = False,
        reduce_only: bool = False,
    ) -> dict:
        """Place a futures order.

        Returns the full order response dict from Binance.
        """
        raw = _to_raw_symbol(symbol)
        params: dict[str, Any] = {
            "symbol": raw,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": qty,
        }
        if order_type.upper() == "LIMIT":
            if price is None:
                raise ValueError("price is required for LIMIT orders")
            params["price"] = price
            params["timeInForce"] = time_in_force
        if post_only:
            params["timeInForce"] = "GTX"  # Binance post-only
        if reduce_only:
            params["reduceOnly"] = "true"

        data = self._signed_post("/fapi/v1/order", params)
        logger.info(
            "Order placed: %s %s %s qty=%.4f price=%s → orderId=%s",
            side.upper(), raw, order_type, qty, price, data.get("orderId"),
        )
        return data

    def fetch_order(self, symbol: str, order_id: int) -> dict:
        """Query a single order by *order_id*."""
        raw = _to_raw_symbol(symbol)
        return self._signed_get(
            "/fapi/v1/order", {"symbol": raw, "orderId": order_id},
        )

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """Cancel an open order."""
        raw = _to_raw_symbol(symbol)
        return self._signed_delete(
            "/fapi/v1/order", {"symbol": raw, "orderId": order_id},
        )

    # ── Account / positions ──────────────────────────────────────────

    def get_positions(self) -> list[dict]:
        """Return all current futures positions (``GET /fapi/v2/positionRisk``).

        Each dict has keys like ``symbol``, ``positionAmt``, ``entryPrice``,
        ``markPrice``, ``unRealizedProfit``, ``notional``, …
        """
        return self._signed_get("/fapi/v2/positionRisk")

    def get_account(self) -> dict:
        """Return full account information (``GET /fapi/v2/account``)."""
        return self._signed_get("/fapi/v2/account")
