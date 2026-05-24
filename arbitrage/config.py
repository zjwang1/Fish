"""
Configuration for US Stock / Binance Futures arbitrage.

Defines tradeable pairs: each entry maps a US-listed stock or ETF
to the corresponding Binance perpetual futures symbol, together with
the hedge ratio (how many units of the futures contract hedge one
share of the stock).
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

# ── Binance credentials ──────────────────────────────────────────────
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
BINANCE_TESTNET = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

# ── Strategy parameters ──────────────────────────────────────────────
SPREAD_THRESHOLD = float(os.getenv("SPREAD_THRESHOLD", "2.0"))  # %
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))            # seconds
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


@dataclass
class ArbPair:
    """One arbitrage relationship."""
    stock_ticker: str          # US stock / ETF ticker  (Yahoo Finance)
    futures_symbol: str        # Binance perpetual      (ccxt unified id)
    hedge_ratio: float = 1.0   # futures_qty = shares * hedge_ratio
    description: str = ""


# ── Pair definitions ─────────────────────────────────────────────────
# Adjust hedge_ratio based on actual correlation / beta.
ARB_PAIRS: list[ArbPair] = [
    ArbPair(
        stock_ticker="MSTR",
        futures_symbol="BTC/USDT:USDT",
        hedge_ratio=0.0025,
        description="MicroStrategy vs BTC futures (MSTR holds ~214k BTC, ~$17B mkt cap)",
    ),
    ArbPair(
        stock_ticker="COIN",
        futures_symbol="BTC/USDT:USDT",
        hedge_ratio=0.001,
        description="Coinbase stock correlated with BTC price",
    ),
    ArbPair(
        stock_ticker="IBIT",
        futures_symbol="BTC/USDT:USDT",
        hedge_ratio=0.00002,
        description="iShares Bitcoin Trust ETF vs BTC futures",
    ),
    ArbPair(
        stock_ticker="ETHE",
        futures_symbol="ETH/USDT:USDT",
        hedge_ratio=0.01,
        description="Grayscale Ethereum Trust vs ETH futures",
    ),
]
