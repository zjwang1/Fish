"""
Configuration for US Stock / Binance Futures funding-rate arbitrage.

Strategy: hold the US-listed stock LONG (via Bit.com Stock API) + SHORT
the same-name Binance perpetual futures contract.  Profit comes from:
  1. Funding rate – when positive, the short side *receives* funding every 8 h.
  2. Basis convergence – any premium/discount between the two venues.

Stock trading is done through the Bit.com (Matrixport) Stock API:
  https://www.bit.com/docs/en-us/stock.html#stock-api
  Base URL: https://mapi.matrixport.com/stock/v1/...

Each ``ArbPair`` maps a Bit.com stock symbol (e.g. ``MU.US``) to its
corresponding Binance perpetual futures symbol (ccxt unified ID).
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

# ── Bit.com (Matrixport) Stock API credentials ──────────────────────
BITCOM_ACCESS_KEY = os.getenv("BITCOM_ACCESS_KEY", "")
BITCOM_SECRET_KEY = os.getenv("BITCOM_SECRET_KEY", "")
BITCOM_BASE_URL = os.getenv("BITCOM_BASE_URL", "https://mapi.matrixport.com")

# ── Binance credentials ──────────────────────────────────────────────
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
BINANCE_TESTNET = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

# ── Strategy parameters ──────────────────────────────────────────────
# Minimum annualised funding-rate yield (%) to consider entry
MIN_FUNDING_APY = float(os.getenv("MIN_FUNDING_APY", "10.0"))
# Maximum acceptable basis (stock-futures) divergence (%) for entry
MAX_BASIS_PCT = float(os.getenv("MAX_BASIS_PCT", "1.0"))
# Default number of shares per trade
DEFAULT_TRADE_QTY = int(os.getenv("DEFAULT_TRADE_QTY", "10"))
# Polling interval in seconds
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── Maker-first execution parameters ────────────────────────────────
# Binance TradFi futures: maker fee = 0, taker fee = 0.04%
# Bit.com stocks: maker/taker ≈ 0.01%
# Strategy: place Binance limit (maker) order first, wait for fill,
# then immediately place Bit.com market (taker) order.
MAKER_ORDER_TIMEOUT = int(os.getenv("MAKER_ORDER_TIMEOUT", "60"))  # seconds
MAKER_POLL_INTERVAL = float(os.getenv("MAKER_POLL_INTERVAL", "0.5"))  # seconds
# Maximum retries for the stock (Bit.com) leg after Binance fills.
# Critical for zero-exposure: we MUST hedge the Binance fill on the stock side.
MAX_STOCK_RETRIES = int(os.getenv("MAX_STOCK_RETRIES", "5"))
# Maximum total position notional value (USD) across all pairs.
# Prevents over-leveraging that could lead to futures liquidation.
# Set to 0 to disable the limit.
MAX_POSITION_VALUE_USD = float(os.getenv("MAX_POSITION_VALUE_USD", "0"))

# Funding is settled every 8 hours on Binance → 3 × 365 = 1095 periods/year
FUNDING_PERIODS_PER_YEAR = 3 * 365


@dataclass
class ArbPair:
    """One funding-rate arbitrage pair.

    The stock and futures represent the **same underlying** asset.
    ``stock_symbol`` uses Bit.com format (e.g. ``MU.US``).
    ``futures_symbol`` uses ccxt unified format (e.g. ``MU/USDT:USDT``).
    """
    stock_symbol: str           # Bit.com stock symbol   (e.g. "MU.US")
    futures_symbol: str         # Binance perp symbol    (ccxt unified id)
    shares_per_contract: float  # how many shares equal 1 futures contract
    description: str = ""

    @property
    def ticker(self) -> str:
        """Short ticker name (e.g. 'MU' from 'MU.US')."""
        return self.stock_symbol.split(".")[0]


# ── Pair definitions ─────────────────────────────────────────────────
# These are US-listed stocks tradeable via Bit.com that also have a
# USDT-margined perpetual contract on Binance.
ARB_PAIRS: list[ArbPair] = [
    ArbPair(
        stock_symbol="MU.US",
        futures_symbol="MU/USDT:USDT",
        shares_per_contract=1.0,
        description="Micron Technology – stock vs MUUSDT perp",
    ),
    ArbPair(
        stock_symbol="AAPL.US",
        futures_symbol="AAPL/USDT:USDT",
        shares_per_contract=1.0,
        description="Apple – stock vs AAPLUSDT perp",
    ),
    ArbPair(
        stock_symbol="TSLA.US",
        futures_symbol="TSLA/USDT:USDT",
        shares_per_contract=1.0,
        description="Tesla – stock vs TSLAUSDT perp",
    ),
    ArbPair(
        stock_symbol="AMZN.US",
        futures_symbol="AMZN/USDT:USDT",
        shares_per_contract=1.0,
        description="Amazon – stock vs AMZNUSDT perp",
    ),
    ArbPair(
        stock_symbol="GOOG.US",
        futures_symbol="GOOG/USDT:USDT",
        shares_per_contract=1.0,
        description="Alphabet – stock vs GOOGUSDT perp",
    ),
    ArbPair(
        stock_symbol="COIN.US",
        futures_symbol="COIN/USDT:USDT",
        shares_per_contract=1.0,
        description="Coinbase – stock vs COINUSDT perp",
    ),
    ArbPair(
        stock_symbol="MSTR.US",
        futures_symbol="MSTR/USDT:USDT",
        shares_per_contract=1.0,
        description="MicroStrategy – stock vs MSTRUSDT perp",
    ),
    ArbPair(
        stock_symbol="NVDA.US",
        futures_symbol="NVDA/USDT:USDT",
        shares_per_contract=1.0,
        description="Nvidia – stock vs NVDAUSDT perp",
    ),
    ArbPair(
        stock_symbol="META.US",
        futures_symbol="META/USDT:USDT",
        shares_per_contract=1.0,
        description="Meta – stock vs METAUSDT perp",
    ),
    ArbPair(
        stock_symbol="MSFT.US",
        futures_symbol="MSFT/USDT:USDT",
        shares_per_contract=1.0,
        description="Microsoft – stock vs MSFTUSDT perp",
    ),
]
