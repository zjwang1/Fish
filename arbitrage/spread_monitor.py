"""
spread_monitor.py – Funding-rate arbitrage monitor.

Strategy:  LONG stock  +  SHORT Binance perpetual futures.

Key metrics tracked per pair:
  • **Basis %** – (futures_price − stock_price) / stock_price × 100.
    A positive basis means the futures trade at a premium → shorting
    futures gives you an immediate "locked-in" profit when the basis
    closes at settlement / convergence.
  • **Funding rate** – the periodic rate (every 8 h on Binance).
    When positive, shorts *receive* funding from longs.
  • **Annualised yield** – funding_rate × 3 × 365 × 100 (%).
  • **Signal** – whether the pair is attractive for entry, hold, or exit.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from config import (
    ArbPair,
    FUNDING_PERIODS_PER_YEAR,
    MAX_BASIS_PCT,
    MIN_FUNDING_APY,
)
from price_fetcher import (
    get_stock_price,
    get_futures_price,
    get_funding_info,
    get_funding_rate_history,
    FundingInfo,
)

logger = logging.getLogger(__name__)


@dataclass
class FundingSnapshot:
    """One point-in-time observation for a funding-rate arb pair."""
    timestamp: datetime
    pair: ArbPair

    # Prices
    stock_price: float
    futures_price: float

    # Basis
    basis_abs: float           # futures_price − stock_price
    basis_pct: float           # basis / stock_price × 100

    # Funding rate
    funding_rate: Optional[float]          # current 8-h rate (e.g. 0.0001)
    funding_apy: Optional[float]           # annualised yield %
    avg_funding_rate: Optional[float]      # avg over recent history
    avg_funding_apy: Optional[float]       # annualised avg yield %
    next_funding_time: Optional[datetime]

    # Signal
    signal: str    # ENTER | HOLD | EXIT | UNFAVORABLE


def _annualise(rate: float) -> float:
    """Convert a single-period funding rate to annualised percentage."""
    return rate * FUNDING_PERIODS_PER_YEAR * 100.0


def compute_snapshot(pair: ArbPair) -> Optional[FundingSnapshot]:
    """Fetch prices + funding data and compute a FundingSnapshot."""

    stock_price = get_stock_price(pair.stock_symbol)
    futures_price = get_futures_price(pair.futures_symbol)

    if stock_price is None or futures_price is None:
        logger.warning(
            "Skipping %s – missing price (stock=%s, futures=%s)",
            pair.ticker, stock_price, futures_price,
        )
        return None

    # ── Basis ────────────────────────────────────────────────────────
    basis_abs = futures_price - stock_price
    basis_pct = (basis_abs / stock_price) * 100.0

    # ── Funding ──────────────────────────────────────────────────────
    fi: Optional[FundingInfo] = get_funding_info(pair.futures_symbol)

    funding_rate: Optional[float] = None
    funding_apy: Optional[float] = None
    next_funding_time: Optional[datetime] = None

    if fi is not None:
        funding_rate = fi.current_rate
        funding_apy = _annualise(fi.current_rate)
        next_funding_time = fi.next_funding_time

    # Average funding rate over recent periods
    history = get_funding_rate_history(pair.futures_symbol, limit=30)
    avg_funding_rate: Optional[float] = None
    avg_funding_apy: Optional[float] = None
    if history:
        rates = [
            h["fundingRate"]
            for h in history
            if h.get("fundingRate") is not None
        ]
        if rates:
            avg_funding_rate = sum(rates) / len(rates)
            avg_funding_apy = _annualise(avg_funding_rate)

    # ── Signal logic ─────────────────────────────────────────────────
    #   ENTER       – funding APY above threshold AND basis within range
    #   HOLD        – already in position, still profitable
    #   EXIT        – funding turned negative (longs pay → shorts pay)
    #   UNFAVORABLE – conditions not met
    effective_apy = avg_funding_apy if avg_funding_apy is not None else funding_apy

    if effective_apy is not None and effective_apy >= MIN_FUNDING_APY:
        if abs(basis_pct) <= MAX_BASIS_PCT:
            signal = "ENTER"
        else:
            signal = "HOLD"   # funding good but basis too wide to enter fresh
    elif funding_rate is not None and funding_rate < 0:
        signal = "EXIT"       # shorts are *paying* → close position
    else:
        signal = "UNFAVORABLE"

    return FundingSnapshot(
        timestamp=datetime.now(timezone.utc),
        pair=pair,
        stock_price=stock_price,
        futures_price=futures_price,
        basis_abs=basis_abs,
        basis_pct=basis_pct,
        funding_rate=funding_rate,
        funding_apy=funding_apy,
        avg_funding_rate=avg_funding_rate,
        avg_funding_apy=avg_funding_apy,
        next_funding_time=next_funding_time,
        signal=signal,
    )


# ── Display helpers ──────────────────────────────────────────────────

_SIGNAL_COLORS = {
    "ENTER": "\033[1;32m",       # green bold
    "HOLD": "\033[1;33m",        # yellow bold
    "EXIT": "\033[1;31m",        # red bold
    "UNFAVORABLE": "\033[0;37m", # grey
}
_RESET = "\033[0m"


def format_snapshot(snap: FundingSnapshot) -> str:
    """Pretty-print a FundingSnapshot for terminal display."""

    def _pct(v: Optional[float]) -> str:
        return f"{v:+.4f}%" if v is not None else "N/A"

    def _apy(v: Optional[float]) -> str:
        return f"{v:+.1f}%" if v is not None else "N/A"

    next_str = (
        snap.next_funding_time.strftime("%H:%M UTC")
        if snap.next_funding_time else "N/A"
    )

    color = _SIGNAL_COLORS.get(snap.signal, "")
    return (
        f"{color}"
        f"[{snap.timestamp:%Y-%m-%d %H:%M:%S UTC}]  "
        f"{snap.pair.ticker:6s} "
        f"Stock ${snap.stock_price:>9.2f}  "
        f"Futures ${snap.futures_price:>9.2f}  │  "
        f"Basis {snap.basis_pct:+.2f}%  │  "
        f"FR {_pct(snap.funding_rate)}  "
        f"APY {_apy(snap.funding_apy)}  "
        f"AvgAPY {_apy(snap.avg_funding_apy)}  "
        f"Next {next_str}  │  "
        f"{snap.signal}"
        f"{_RESET}"
    )
