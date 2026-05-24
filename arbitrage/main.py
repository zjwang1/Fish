#!/usr/bin/env python3
"""
main.py – Entry-point for the US-Stock ↔ Binance-Futures funding-rate
arbitrage monitor.

Strategy:  LONG US stock  +  SHORT Binance perpetual futures.
Profit = funding rate (paid to shorts when positive) + basis convergence.

Usage:
    python main.py              # live monitor (prints to terminal)
    python main.py --once       # single snapshot then exit
    python main.py --csv out.csv  # append every snapshot to a CSV file
"""

import argparse
import csv
import logging
import os
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
        "timestamp", "stock_ticker", "stock_price",
        "futures_symbol", "futures_price",
        "basis_pct", "funding_rate", "funding_apy",
        "avg_funding_rate", "avg_funding_apy",
        "next_funding_time", "signal",
    ]


def _snap_to_row(snap: FundingSnapshot) -> list[str]:
    return [
        snap.timestamp.isoformat(),
        snap.pair.stock_ticker,
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


def run_once(csv_path: str | None = None) -> None:
    """Fetch and display a single round of snapshots."""
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

    # Optional CSV logging
    if csv_path:
        file_exists = Path(csv_path).exists()
        with open(csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(_csv_header())
            for snap in snapshots:
                writer.writerow(_snap_to_row(snap))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="US Stock ↔ Binance Futures Funding-Rate Arbitrage Monitor\n\n"
                    "Strategy: LONG stock + SHORT Binance perp → earn funding rate",
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
    args = parser.parse_args()

    _setup_logging()

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   Funding-Rate Arbitrage: LONG Stock + SHORT Binance Perp  ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  Pairs: {len(ARB_PAIRS)}  |  "
          f"Min APY: {MIN_FUNDING_APY:.1f}%  |  "
          f"Max Basis: {MAX_BASIS_PCT:.1f}%  |  "
          f"Interval: {POLL_INTERVAL}s")
    print("-" * 140)
    for pair in ARB_PAIRS:
        print(f"  {pair.stock_ticker:6s} ↔ {pair.futures_symbol:20s}  ({pair.description})")
    print("-" * 140)

    if args.once:
        run_once(csv_path=args.csv)
        return

    # Continuous loop
    try:
        while True:
            run_once(csv_path=args.csv)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\nStopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
