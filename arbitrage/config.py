"""
Configuration for US Stock / Binance Futures funding-rate arbitrage.

Strategy: hold the US-listed stock LONG  +  SHORT the same-name Binance
perpetual futures contract.  Profit comes from:
  1. Funding rate – when positive, the short side *receives* funding every 8 h.
  2. Basis convergence – any premium/discount between the two venues.

Each ``ArbPair`` maps a US stock ticker (Yahoo Finance) to its corresponding
Binance perpetual futures symbol (ccxt unified ID).  The ``contract_size``
field records how many USDT one futures contract represents so we can
convert between share-denominated and contract-denominated quantities.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

# ── Binance credentials ──────────────────────────────────────────────
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
BINANCE_TESTNET = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

# ── Strategy parameters ──────────────────────────────────────────────
# Minimum annualised funding-rate yield (%) to consider entry
MIN_FUNDING_APY = float(os.getenv("MIN_FUNDING_APY", "10.0"))
# Maximum acceptable basis (stock-futures) divergence (%) for entry
MAX_BASIS_PCT = float(os.getenv("MAX_BASIS_PCT", "1.0"))
# Polling interval in seconds
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Funding is settled every 8 hours on Binance → 3 × 365 = 1095 periods/year
FUNDING_PERIODS_PER_YEAR = 3 * 365


@dataclass
class ArbPair:
    """One funding-rate arbitrage pair.

    The stock and futures represent the **same underlying** asset, so
    1 share ≈ ``shares_per_contract`` contracts on Binance.
    """
    stock_ticker: str           # US stock ticker        (Yahoo Finance)
    futures_symbol: str         # Binance perp symbol    (ccxt unified id)
    shares_per_contract: float  # how many shares equal 1 futures contract
    description: str = ""


# ── Pair definitions ─────────────────────────────────────────────────
# These are US-listed stocks that also have a USDT-margined perpetual
# contract on Binance (under the ``xxxUSDT`` naming convention).
# ``shares_per_contract`` should be calibrated so that the dollar
# exposure on both legs is roughly equal.
ARB_PAIRS: list[ArbPair] = [
    ArbPair(
        stock_ticker="MU",
        futures_symbol="MU/USDT:USDT",
        shares_per_contract=1.0,
        description="Micron Technology – stock vs MUUSDT perp",
    ),
    ArbPair(
        stock_ticker="AAPL",
        futures_symbol="AAPL/USDT:USDT",
        shares_per_contract=1.0,
        description="Apple – stock vs AAPLUSDT perp",
    ),
    ArbPair(
        stock_ticker="TSLA",
        futures_symbol="TSLA/USDT:USDT",
        shares_per_contract=1.0,
        description="Tesla – stock vs TSLAUSDT perp",
    ),
    ArbPair(
        stock_ticker="AMZN",
        futures_symbol="AMZN/USDT:USDT",
        shares_per_contract=1.0,
        description="Amazon – stock vs AMNZUSDT perp",
    ),
    ArbPair(
        stock_ticker="GOOG",
        futures_symbol="GOOG/USDT:USDT",
        shares_per_contract=1.0,
        description="Alphabet – stock vs GOOGUSDT perp",
    ),
    ArbPair(
        stock_ticker="COIN",
        futures_symbol="COIN/USDT:USDT",
        shares_per_contract=1.0,
        description="Coinbase – stock vs COINUSDT perp",
    ),
    ArbPair(
        stock_ticker="MSTR",
        futures_symbol="MSTR/USDT:USDT",
        shares_per_contract=1.0,
        description="MicroStrategy – stock vs MSTRUSDT perp",
    ),
    ArbPair(
        stock_ticker="NVDA",
        futures_symbol="NVDA/USDT:USDT",
        shares_per_contract=1.0,
        description="Nvidia – stock vs NVDAUSDT perp",
    ),
    ArbPair(
        stock_ticker="META",
        futures_symbol="META/USDT:USDT",
        shares_per_contract=1.0,
        description="Meta – stock vs METAUSDT perp",
    ),
    ArbPair(
        stock_ticker="MSFT",
        futures_symbol="MSFT/USDT:USDT",
        shares_per_contract=1.0,
        description="Microsoft – stock vs MSFTUSDT perp",
    ),
]
