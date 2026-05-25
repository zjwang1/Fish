#!/usr/bin/env python3
"""
backtest.py – Historical backtest for the funding-rate arbitrage strategy.

Fetches historical funding rates from the Binance public REST API and
simulates the LONG stock + SHORT futures strategy to estimate annualised
returns.  No API key required – only public endpoints are used.

Signal logic (mirrors spread_monitor.py):
  ENTER – avg funding APY ≥ MIN_FUNDING_APY  AND  |basis| ≤ MAX_BASIS_PCT
  EXIT  – rolling-average funding APY < 0
          AND held ≥ MIN_HOLD_PERIODS (default 48 h)
          AND cumulative funding already covers round-trip fee

Assumptions / simplifications:
  • Stock price is approximated by futures mark price (no separate stock
    historical data needed – for TradFi stock-mirroring perps the prices
    track closely).
  • Entry / exit happen at the settlement price (no slippage model).
  • Fees:  Binance maker  = 0 %
          Bit.com taker  = 0.01 % (per leg, entry + exit = 0.02 %)
  • Funding payments are received exactly at the recorded rate each 8 h.

Usage:
    python backtest.py                         # all configured pairs, 90 days
    python backtest.py --days 180              # last 180 days
    python backtest.py --symbol MUUSDT         # single symbol
    python backtest.py --min-apy 15            # override entry threshold
    python backtest.py --csv results.csv       # export trades to CSV
"""

import argparse
import csv
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import requests

from config import (
    ARB_PAIRS,
    ArbPair,
    FUNDING_PERIODS_PER_YEAR,
    MAX_BASIS_PCT,
    MIN_FUNDING_APY,
    MIN_HOLD_PERIODS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Fee assumptions ──────────────────────────────────────────────────
# Binance maker = 0, Bit.com taker ≈ 0.01%.  Each round trip = 2 × 0.01%
ROUND_TRIP_FEE_PCT = 0.02  # percent


# ── Data structures ──────────────────────────────────────────────────

@dataclass
class BacktestTrade:
    """One round-trip (entry → exit) in the backtest."""
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    funding_collected: float    # cumulative funding rate sum over hold
    funding_pnl_pct: float      # funding PnL as % of notional
    basis_pnl_pct: float        # basis convergence PnL %
    fee_pct: float              # fees %
    net_pnl_pct: float          # net PnL %
    hold_hours: float


@dataclass
class BacktestResult:
    """Aggregate result for one pair."""
    pair: ArbPair
    days_tested: int
    total_funding_records: int
    num_trades: int
    avg_hold_hours: float
    total_funding_pnl_pct: float
    total_basis_pnl_pct: float
    total_fee_pct: float
    total_net_pnl_pct: float
    annualised_return_pct: float
    time_in_position_pct: float   # % of time holding a position
    trades: list[BacktestTrade] = field(default_factory=list)


# ── Binance REST API helpers ─────────────────────────────────────────

BINANCE_FAPI_BASE = "https://fapi.binance.com"


def _unified_to_binance(symbol: str) -> str:
    """Convert unified symbol to Binance raw symbol.

    Examples:
        'MU/USDT:USDT' → 'MUUSDT'
        'AAPL/USDT:USDT' → 'AAPLUSDT'
    """
    base = symbol.split(":")[0]   # 'MU/USDT'
    return base.replace("/", "")  # 'MUUSDT'


# ── Data fetching ────────────────────────────────────────────────────

def fetch_all_funding_history(
    symbol: str,
    since_ms: int,
    until_ms: int,
) -> list[dict]:
    """Fetch complete funding rate history by paginating through the Binance API.

    Uses the public endpoint ``GET /fapi/v1/fundingRate`` which requires
    no API key.  Returns records in the same shape consumed by the
    backtest engine (keys: timestamp, fundingRate, markPrice).
    """
    raw_symbol = _unified_to_binance(symbol)
    url = f"{BINANCE_FAPI_BASE}/fapi/v1/fundingRate"
    all_records: list[dict] = []
    cursor = since_ms

    while cursor < until_ms:
        params = {
            "symbol": raw_symbol,
            "startTime": cursor,
            "endTime": until_ms,
            "limit": 1000,
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            batch = resp.json()
        except Exception as e:
            logger.error("Failed to fetch funding history for %s: %s", symbol, e)
            break

        if not batch:
            break

        for item in batch:
            all_records.append({
                "timestamp": int(item["fundingTime"]),
                "fundingRate": float(item["fundingRate"]),
                "markPrice": float(item.get("markPrice", 0)),
            })

        last_ts = int(batch[-1]["fundingTime"])
        if last_ts <= cursor:
            break  # no progress
        cursor = last_ts + 1

        # Be nice to the API
        time.sleep(0.2)

    # Filter to the requested window
    return [r for r in all_records if since_ms <= r["timestamp"] <= until_ms]


# ── Backtest engine ──────────────────────────────────────────────────

def run_pair_backtest(
    pair: ArbPair,
    days: int,
    min_funding_apy: float,
    max_basis_pct: float,
    avg_window: int = 30,
    min_hold_periods: int = MIN_HOLD_PERIODS,
) -> Optional[BacktestResult]:
    """Run backtest for a single pair."""

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    since_ms = now_ms - days * 24 * 60 * 60 * 1000

    logger.info("Fetching funding history for %s (%d days)...", pair.futures_symbol, days)
    records = fetch_all_funding_history(pair.futures_symbol, since_ms, now_ms)

    if not records:
        logger.warning("No funding data for %s", pair.futures_symbol)
        return None

    logger.info("  Got %d funding records for %s", len(records), pair.ticker)

    # Sort by timestamp
    records.sort(key=lambda r: r["timestamp"])

    # Extract time series
    timestamps = [
        datetime.fromtimestamp(r["timestamp"] / 1000, tz=timezone.utc)
        for r in records
    ]
    rates = [float(r.get("fundingRate", 0)) for r in records]
    # Use mark price as proxy for both stock and futures price
    prices = [
        float(r.get("markPrice") or r.get("indexPrice") or 0)
        for r in records
    ]

    # ── Simulate ─────────────────────────────────────────────────────
    trades: list[BacktestTrade] = []
    in_position = False
    entry_idx = 0
    cumulative_funding = 0.0
    periods_held = 0

    # Fee breakeven: cumulative funding (as fraction, not %) must exceed
    # round-trip fee before we consider closing.
    fee_breakeven = ROUND_TRIP_FEE_PCT / 100.0   # 0.0002

    for i in range(avg_window, len(records)):
        rate = rates[i]
        price = prices[i]
        if price <= 0:
            continue

        # Compute rolling average APY (same as live code)
        window_rates = rates[max(0, i - avg_window + 1): i + 1]
        avg_rate = sum(window_rates) / len(window_rates)
        avg_apy = avg_rate * FUNDING_PERIODS_PER_YEAR * 100.0

        # Hedged strategy: LONG stock + SHORT futures.  Since we use
        # the same mark price for both legs, directional price moves
        # cancel out → basis PnL = 0.  The sole PnL source is funding.

        if not in_position:
            # ── Entry signal ─────────────────────────────────────────
            if avg_apy >= min_funding_apy:
                in_position = True
                entry_idx = i
                cumulative_funding = 0.0
                periods_held = 0
        else:
            # Collect funding
            cumulative_funding += rate
            periods_held += 1

            # ── Exit signal ──────────────────────────────────────────
            # Three guards prevent premature exits that waste fees:
            #  1. Minimum hold period (MIN_HOLD_PERIODS, default 48 h)
            #  2. Rolling-average APY must be negative (trend, not noise)
            #  3. Fee-breakeven: cumulative funding must have covered the
            #     round-trip fee – otherwise closing locks in a net loss
            can_exit = (
                periods_held >= min_hold_periods
                and avg_apy < 0
                and cumulative_funding >= fee_breakeven
            )
            if can_exit:
                entry_time = timestamps[entry_idx]
                exit_time = timestamps[i]
                entry_price = prices[entry_idx]
                exit_price = price

                hold_hours = (exit_time - entry_time).total_seconds() / 3600
                funding_pnl_pct = cumulative_funding * 100.0

                # Basis PnL: In a hedged strategy (LONG stock + SHORT futures),
                # the stock and futures prices move together, so directional
                # price moves cancel out.  Since we use the same mark price
                # as proxy for both legs, the hedged basis PnL is 0.
                # (Short futures loses when price rises, but long stock gains
                #  the same amount — net directional exposure = 0.)
                basis_pnl_pct = 0.0

                fee_pct = ROUND_TRIP_FEE_PCT
                net_pnl_pct = funding_pnl_pct + basis_pnl_pct - fee_pct

                trades.append(BacktestTrade(
                    symbol=pair.futures_symbol,
                    entry_time=entry_time,
                    exit_time=exit_time,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    funding_collected=cumulative_funding,
                    funding_pnl_pct=funding_pnl_pct,
                    basis_pnl_pct=basis_pnl_pct,
                    fee_pct=fee_pct,
                    net_pnl_pct=net_pnl_pct,
                    hold_hours=hold_hours,
                ))

                in_position = False

    # Close any open position at end of data
    if in_position and len(records) > entry_idx:
        i = len(records) - 1
        entry_time = timestamps[entry_idx]
        exit_time = timestamps[i]
        entry_price = prices[entry_idx]
        exit_price = prices[i]

        hold_hours = (exit_time - entry_time).total_seconds() / 3600
        funding_pnl_pct = cumulative_funding * 100.0
        # Hedged strategy: stock + futures cancel out directional moves
        basis_pnl_pct = 0.0
        fee_pct = ROUND_TRIP_FEE_PCT
        net_pnl_pct = funding_pnl_pct + basis_pnl_pct - fee_pct

        trades.append(BacktestTrade(
            symbol=pair.futures_symbol,
            entry_time=entry_time,
            exit_time=exit_time,
            entry_price=entry_price,
            exit_price=exit_price,
            funding_collected=cumulative_funding,
            funding_pnl_pct=funding_pnl_pct,
            basis_pnl_pct=basis_pnl_pct,
            fee_pct=fee_pct,
            net_pnl_pct=net_pnl_pct,
            hold_hours=hold_hours,
        ))

    # ── Aggregate ────────────────────────────────────────────────────
    total_funding_pnl = sum(t.funding_pnl_pct for t in trades)
    total_basis_pnl = sum(t.basis_pnl_pct for t in trades)
    total_fee = sum(t.fee_pct for t in trades)
    total_net = sum(t.net_pnl_pct for t in trades)
    total_hold_hours = sum(t.hold_hours for t in trades)
    avg_hold = total_hold_hours / len(trades) if trades else 0

    total_hours = days * 24
    time_in_pct = (total_hold_hours / total_hours) * 100 if total_hours > 0 else 0

    # Annualise: scale net PnL by (365 / days_tested)
    annualised = (total_net / days * 365) if days > 0 else 0

    return BacktestResult(
        pair=pair,
        days_tested=days,
        total_funding_records=len(records),
        num_trades=len(trades),
        avg_hold_hours=avg_hold,
        total_funding_pnl_pct=total_funding_pnl,
        total_basis_pnl_pct=total_basis_pnl,
        total_fee_pct=total_fee,
        total_net_pnl_pct=total_net,
        annualised_return_pct=annualised,
        time_in_position_pct=time_in_pct,
        trades=trades,
    )


# ── Display ──────────────────────────────────────────────────────────

def print_result(r: BacktestResult) -> None:
    """Pretty-print a single pair's backtest result."""
    print(f"\n{'─' * 70}")
    print(f"  {r.pair.ticker:6s}  ({r.pair.description})")
    print(f"{'─' * 70}")
    print(f"  Period:              {r.days_tested} days  ({r.total_funding_records} funding records)")
    print(f"  Trades:              {r.num_trades}")
    print(f"  Avg hold:            {r.avg_hold_hours:.1f} hours ({r.avg_hold_hours / 24:.1f} days)")
    print(f"  Time in position:    {r.time_in_position_pct:.1f}%")
    print()
    print(f"  Funding PnL:         {r.total_funding_pnl_pct:+.4f}%")
    print(f"  Basis PnL:           {r.total_basis_pnl_pct:+.4f}%")
    print(f"  Fees:                {r.total_fee_pct:-.4f}%")
    print(f"  ────────────────────────────")
    print(f"  Net PnL:             {r.total_net_pnl_pct:+.4f}%")
    print(f"  Annualised return:   {r.annualised_return_pct:+.2f}%")

    if r.trades:
        print(f"\n  {'#':>3s}  {'Entry':19s}  {'Exit':19s}  {'Hold(h)':>8s}  "
              f"{'Fund%':>8s}  {'Basis%':>8s}  {'Net%':>8s}")
        for idx, t in enumerate(r.trades, 1):
            print(
                f"  {idx:3d}  "
                f"{t.entry_time:%Y-%m-%d %H:%M}  "
                f"{t.exit_time:%Y-%m-%d %H:%M}  "
                f"{t.hold_hours:8.1f}  "
                f"{t.funding_pnl_pct:+8.4f}  "
                f"{t.basis_pnl_pct:+8.4f}  "
                f"{t.net_pnl_pct:+8.4f}"
            )


def print_summary(results: list[BacktestResult]) -> None:
    """Print portfolio-level summary."""
    valid = [r for r in results if r.num_trades > 0]
    if not valid:
        print("\n  No trades were generated across any pair.")
        return

    print(f"\n{'═' * 70}")
    print("  PORTFOLIO SUMMARY")
    print(f"{'═' * 70}")

    print(f"\n  {'Ticker':8s}  {'Trades':>6s}  {'Fund%':>8s}  {'Basis%':>8s}  "
          f"{'Net%':>8s}  {'Ann%':>8s}  {'InPos%':>6s}")
    print(f"  {'─' * 62}")

    total_net = 0.0
    total_trades = 0
    for r in results:
        print(
            f"  {r.pair.ticker:8s}  "
            f"{r.num_trades:6d}  "
            f"{r.total_funding_pnl_pct:+8.4f}  "
            f"{r.total_basis_pnl_pct:+8.4f}  "
            f"{r.total_net_pnl_pct:+8.4f}  "
            f"{r.annualised_return_pct:+8.2f}  "
            f"{r.time_in_position_pct:5.1f}%"
        )
        total_net += r.total_net_pnl_pct
        total_trades += r.num_trades

    # Equal-weight portfolio average
    avg_net = total_net / len(results)
    days = results[0].days_tested if results else 90
    avg_ann = (avg_net / days * 365) if days > 0 else 0

    print(f"  {'─' * 62}")
    print(f"  {'AVG':8s}  {total_trades:6d}  {'':8s}  {'':8s}  "
          f"{avg_net:+8.4f}  {avg_ann:+8.2f}")
    print()
    print(f"  Equal-weight portfolio estimated annualised return: {avg_ann:+.2f}%")
    print(f"  (based on {days}-day backtest across {len(results)} pairs)")


def export_csv(results: list[BacktestResult], path: str) -> None:
    """Export all trades to a CSV file."""
    header = [
        "symbol", "entry_time", "exit_time",
        "entry_price", "exit_price",
        "hold_hours", "funding_pnl_pct", "basis_pnl_pct",
        "fee_pct", "net_pnl_pct",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for r in results:
            for t in r.trades:
                writer.writerow([
                    t.symbol,
                    t.entry_time.isoformat(),
                    t.exit_time.isoformat(),
                    f"{t.entry_price:.4f}",
                    f"{t.exit_price:.4f}",
                    f"{t.hold_hours:.1f}",
                    f"{t.funding_pnl_pct:.6f}",
                    f"{t.basis_pnl_pct:.6f}",
                    f"{t.fee_pct:.6f}",
                    f"{t.net_pnl_pct:.6f}",
                ])
    print(f"\n  📁 Trades exported to {path}")


# ── CLI ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtest funding-rate arbitrage strategy using Binance historical data.\n\n"
                    "Strategy: LONG stock + SHORT Binance perp → collect positive funding rate.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--days", type=int, default=90,
        help="Number of days to backtest (default: 90)",
    )
    parser.add_argument(
        "--symbol", type=str, default=None,
        help="Filter to a single Binance symbol (e.g. MUUSDT). "
             "Matches against the futures symbol or ticker name.",
    )
    parser.add_argument(
        "--min-apy", type=float, default=None,
        help=f"Override MIN_FUNDING_APY (default: {MIN_FUNDING_APY}%%)",
    )
    parser.add_argument(
        "--max-basis", type=float, default=None,
        help=f"Override MAX_BASIS_PCT (default: {MAX_BASIS_PCT}%%)",
    )
    parser.add_argument(
        "--avg-window", type=int, default=30,
        help="Rolling window size for avg funding rate (default: 30 periods = 10 days)",
    )
    parser.add_argument(
        "--min-hold", type=int, default=None,
        help=f"Minimum hold periods before exit is considered "
             f"(default: {MIN_HOLD_PERIODS}, each period = 8 h)",
    )
    parser.add_argument(
        "--csv", type=str, default=None, metavar="FILE",
        help="Export trade details to a CSV file",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show individual trade details for each pair",
    )
    args = parser.parse_args()

    min_apy = args.min_apy if args.min_apy is not None else MIN_FUNDING_APY
    max_basis = args.max_basis if args.max_basis is not None else MAX_BASIS_PCT
    min_hold = args.min_hold if args.min_hold is not None else MIN_HOLD_PERIODS

    # Filter pairs
    pairs = ARB_PAIRS
    if args.symbol:
        target = args.symbol.upper()
        pairs = [
            p for p in ARB_PAIRS
            if target in p.futures_symbol.upper() or target == p.ticker.upper()
        ]
        if not pairs:
            print(f"No pair found matching '{args.symbol}'")
            sys.exit(1)

    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║     Funding-Rate Arbitrage Backtest                            ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print(f"  Period: {args.days} days  |  Min APY: {min_apy:.1f}%  |  "
          f"Max Basis: {max_basis:.1f}%  |  Avg Window: {args.avg_window}")
    print(f"  Pairs: {len(pairs)}  |  Fees: {ROUND_TRIP_FEE_PCT:.2f}% round-trip  |  "
          f"Min Hold: {min_hold} periods ({min_hold * 8}h)")
    print(f"  Signal: ENTER when avg_funding_apy ≥ {min_apy:.1f}%")
    print(f"          EXIT  when avg_funding_apy < 0 AND held ≥ {min_hold} periods AND fees covered")

    results: list[BacktestResult] = []

    for pair in pairs:
        try:
            result = run_pair_backtest(
                pair, args.days,
                min_funding_apy=min_apy,
                max_basis_pct=max_basis,
                avg_window=args.avg_window,
                min_hold_periods=min_hold,
            )
        except Exception as e:
            logger.error("Backtest failed for %s: %s", pair.ticker, e)
            result = None

        if result is not None:
            results.append(result)
            if args.verbose:
                print_result(result)
            else:
                ann = result.annualised_return_pct
                icon = "✅" if ann > 0 else "⚠️"
                print(f"  {icon} {result.pair.ticker:8s}  "
                      f"trades={result.num_trades:3d}  "
                      f"net={result.total_net_pnl_pct:+.4f}%  "
                      f"ann={ann:+.2f}%")

    if results:
        print_summary(results)

    if args.csv and results:
        export_csv(results, args.csv)


if __name__ == "__main__":
    main()
