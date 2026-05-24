#!/usr/bin/env python3
"""
main.py – Entry-point for the US-Stock ↔ Binance-Futures arbitrage monitor.

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

from config import ARB_PAIRS, POLL_INTERVAL, LOG_LEVEL
from spread_monitor import compute_spread, format_snapshot, SpreadSnapshot


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
        "implied_crypto_price", "spread_pct",
        "funding_rate", "signal",
    ]


def _snap_to_row(snap: SpreadSnapshot) -> list[str]:
    return [
        snap.timestamp.isoformat(),
        snap.pair.stock_ticker,
        f"{snap.stock_price:.4f}",
        snap.pair.futures_symbol,
        f"{snap.futures_price:.4f}",
        f"{snap.implied_stock_crypto:.4f}",
        f"{snap.spread_pct:.4f}",
        f"{snap.funding_rate:.6f}" if snap.funding_rate is not None else "",
        snap.signal,
    ]


def run_once(csv_path: str | None = None) -> None:
    """Fetch and display a single round of snapshots."""
    snapshots: list[SpreadSnapshot] = []
    for pair in ARB_PAIRS:
        snap = compute_spread(pair)
        if snap is not None:
            snapshots.append(snap)

    if not snapshots:
        print("No data available – market may be closed or API keys missing.")
        return

    # Terminal output
    print("=" * 130)
    for snap in snapshots:
        line = format_snapshot(snap)
        # Highlight actionable signals
        if snap.signal != "NEUTRAL":
            print(f"\033[1;33m{line}\033[0m")  # yellow bold
        else:
            print(line)
    print("=" * 130)

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
        description="US Stock ↔ Binance Futures Arbitrage Monitor"
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
    logger = logging.getLogger(__name__)

    print(f"Monitoring {len(ARB_PAIRS)} pairs | "
          f"Spread threshold: {float(os.getenv('SPREAD_THRESHOLD', '2.0')):.1f}% | "
          f"Interval: {POLL_INTERVAL}s")
    print("-" * 130)
    for pair in ARB_PAIRS:
        print(f"  {pair.stock_ticker:6s} ↔ {pair.futures_symbol:16s}  "
              f"hedge_ratio={pair.hedge_ratio}  ({pair.description})")
    print("-" * 130)

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
