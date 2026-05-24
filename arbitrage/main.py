#!/usr/bin/env python3
"""
main.py – Entry-point for the US-Stock ↔ Binance-Futures funding-rate
arbitrage monitor and trader.

Strategy:  LONG US stock (via Bit.com)  +  SHORT Binance perpetual futures.
Profit = funding rate (paid to shorts when positive) + basis convergence.

Usage:
    python main.py              # live monitor (prints to terminal)
    python main.py --once       # single snapshot then exit
    python main.py --csv out.csv  # append every snapshot to a CSV file
    python main.py --trade      # enable live trading (opens/closes positions)
    python main.py --positions  # show current positions on both venues
"""

import argparse
import csv
import logging
import sys
import time
from pathlib import Path

from config import ARB_PAIRS, POLL_INTERVAL, LOG_LEVEL, MIN_FUNDING_APY, MAX_BASIS_PCT
from spread_monitor import compute_snapshot, format_snapshot, FundingSnapshot


def _setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _csv_header() -> list[str]:
    return [
        "timestamp", "stock_symbol", "stock_price",
        "futures_symbol", "futures_price",
        "basis_pct", "funding_rate", "funding_apy",
        "avg_funding_rate", "avg_funding_apy",
        "next_funding_time", "signal",
    ]


def _snap_to_row(snap: FundingSnapshot) -> list[str]:
    return [
        snap.timestamp.isoformat(),
        snap.pair.stock_symbol,
        f"{snap.stock_price:.4f}",
        snap.pair.futures_symbol,
        f"{snap.futures_price:.4f}",
        f"{snap.basis_pct:.4f}",
        f"{snap.funding_rate:.6f}" if snap.funding_rate is not None else "",
        f"{snap.funding_apy:.2f}" if snap.funding_apy is not None else "",
        f"{snap.avg_funding_rate:.6f}" if snap.avg_funding_rate is not None else "",
        f"{snap.avg_funding_apy:.2f}" if snap.avg_funding_apy is not None else "",
        snap.next_funding_time.isoformat() if snap.next_funding_time else "",
        snap.signal,
    ]


def run_once(
    csv_path: str | None = None,
    trade_enabled: bool = False,
) -> None:
    """Fetch and display a single round of snapshots, optionally trade."""
    snapshots: list[FundingSnapshot] = []
    for pair in ARB_PAIRS:
        snap = compute_snapshot(pair)
        if snap is not None:
            snapshots.append(snap)

    if not snapshots:
        print("No data available – market may be closed or API keys missing.")
        return

    # Sort: best signals first (ENTER > HOLD > UNFAVORABLE > EXIT)
    signal_order = {"ENTER": 0, "HOLD": 1, "UNFAVORABLE": 2, "EXIT": 3}
    snapshots.sort(key=lambda s: signal_order.get(s.signal, 99))

    # Terminal output
    print("=" * 140)
    for snap in snapshots:
        print(format_snapshot(snap))
    print("=" * 140)

    # Summary
    enter_count = sum(1 for s in snapshots if s.signal == "ENTER")
    exit_count = sum(1 for s in snapshots if s.signal == "EXIT")
    if enter_count:
        print(f"  ✅ {enter_count} pair(s) with ENTER signal")
    if exit_count:
        print(f"  🚨 {exit_count} pair(s) with EXIT signal (funding negative)")

    # Live trading
    if trade_enabled:
        _execute_signals(snapshots)

    # Optional CSV logging
    if csv_path:
        file_exists = Path(csv_path).exists()
        with open(csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(_csv_header())
            for snap in snapshots:
                writer.writerow(_snap_to_row(snap))


def _execute_signals(snapshots: list[FundingSnapshot]) -> None:
    """Execute trades based on signals (only when --trade is enabled)."""
    from trader import (
        open_arb_position,
        close_arb_position,
        format_trade_result,
        get_stock_positions,
    )

    # Get current stock positions to avoid duplicates
    try:
        stock_positions = get_stock_positions()
    except Exception:
        stock_positions = {}

    for snap in snapshots:
        has_position = snap.pair.stock_symbol in stock_positions

        if snap.signal == "ENTER" and not has_position:
            print(f"\n  📈 Opening position: {snap.pair.ticker} ...")
            result = open_arb_position(
                snap.pair,
                stock_price=snap.stock_price,
                futures_price=snap.futures_price,
            )
            print(f"  {format_trade_result(result)}")

        elif snap.signal == "EXIT" and has_position:
            print(f"\n  📉 Closing position: {snap.pair.ticker} ...")
            qty = int(stock_positions.get(snap.pair.stock_symbol, 0))
            if qty > 0:
                result = close_arb_position(
                    snap.pair,
                    qty=qty,
                    stock_price=snap.stock_price,
                    futures_price=snap.futures_price,
                )
                print(f"  {format_trade_result(result)}")


def show_positions() -> None:
    """Display current positions on both Bit.com and Binance."""
    from trader import get_stock_positions, get_futures_positions

    print("\n╔══════════════════════════════════════════════╗")
    print("║           Current Positions                  ║")
    print("╚══════════════════════════════════════════════╝")

    print("\n  📊 Stock Positions (Bit.com):")
    stock_pos = get_stock_positions()
    if stock_pos:
        for symbol, qty in stock_pos.items():
            print(f"    {symbol:12s}  qty={qty:.0f}")
    else:
        print("    (none)")

    print("\n  📊 Futures Positions (Binance):")
    futures_pos = get_futures_positions()
    if futures_pos:
        for symbol, qty in futures_pos.items():
            direction = "SHORT" if qty < 0 else "LONG"
            print(f"    {symbol:20s}  {direction} qty={abs(qty):.4f}")
    else:
        print("    (none)")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="US Stock ↔ Binance Futures Funding-Rate Arbitrage\n\n"
                    "Strategy: LONG stock (Bit.com) + SHORT Binance perp → earn funding rate",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single snapshot and exit",
    )
    parser.add_argument(
        "--csv", type=str, default=None, metavar="FILE",
        help="Append snapshots to a CSV file",
    )
    parser.add_argument(
        "--trade", action="store_true",
        help="Enable live trading (opens/closes positions based on signals)",
    )
    parser.add_argument(
        "--positions", action="store_true",
        help="Show current positions on both venues and exit",
    )
    args = parser.parse_args()

    _setup_logging()

    if args.positions:
        show_positions()
        return

    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  Funding-Rate Arbitrage: LONG Stock (Bit.com) + SHORT Binance  ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    trade_label = " 🔴 LIVE TRADING" if args.trade else ""
    print(f"  Pairs: {len(ARB_PAIRS)}  |  "
          f"Min APY: {MIN_FUNDING_APY:.1f}%  |  "
          f"Max Basis: {MAX_BASIS_PCT:.1f}%  |  "
          f"Interval: {POLL_INTERVAL}s{trade_label}")
    print("-" * 140)
    for pair in ARB_PAIRS:
        print(f"  {pair.stock_symbol:10s} ↔ {pair.futures_symbol:20s}  ({pair.description})")
    print("-" * 140)

    if args.trade:
        print("\n  ⚠️  LIVE TRADING ENABLED – orders will be placed on Bit.com & Binance!")
        print("  Press Ctrl+C to stop.\n")

    if args.once:
        run_once(csv_path=args.csv, trade_enabled=args.trade)
        return

    # Continuous loop
    try:
        while True:
            run_once(csv_path=args.csv, trade_enabled=args.trade)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\nStopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
