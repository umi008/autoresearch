"""
Data preparation script — download and cache historical OHLCV data.
Run this before starting the agent for the first time or to refresh data.
"""

from __future__ import annotations

import argparse
from datetime import datetime

import data
from loguru import logger

# ─── Assets to download (Forex + Gold only) ───────────────────────────────────
ASSETS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "XAUUSD"]

# ─── Timeframes ────────────────────────────────────────────────────────────────
TIMEFRAMES = ["M15", "H1", "H4"]

# ─── Bars to download (M15 ≈ 5000 bars ≈ 52 days) ─────────────────────────────
DEFAULT_BARS = {
    "M15": 5000,
    "H1": 2000,
    "H4": 1000,
}


def download_all(timeframe: str = "M15", bars: int = 5000, force: bool = False) -> None:
    """Download data for all assets."""
    logger.info(f"Downloading {bars} bars of {timeframe} for {len(ASSETS)} assets...")
    
    if force:
        logger.info("Force mode: clearing cache first")
        data.clear_cache()
    
    for asset in ASSETS:
        try:
            df = data.get_ohlcv(asset, timeframe, bars)
            logger.info(f"  ✓ {asset}: {len(df)} rows")
        except Exception as e:
            logger.error(f"  ✗ {asset}: {e}")
    
    logger.info("Download complete!")


def download_multi_timeframe(bars: int = 5000, force: bool = False) -> None:
    """Download data for multiple timeframes."""
    for tf in TIMEFRAMES:
        b = DEFAULT_BARS.get(tf, bars)
        logger.info(f"\n{'='*50}\nDownloading {tf} data...\n{'='*50}")
        download_all(tf, b, force)


def check_data_integrity() -> None:
    """Check cached data for completeness."""
    logger.info("Checking data integrity...")
    
    issues = []
    
    for asset in ASSETS:
        for tf in ["M15"]:
            bars = DEFAULT_BARS.get(tf, 5000)
            try:
                df = data.get_ohlcv(asset, tf, 10)  # Small sample
                if df.empty:
                    issues.append(f"{asset}/{tf}: empty DataFrame")
                elif df["timestamp"].iloc[-1] < datetime(2024, 1, 1, tzinfo=None):
                    issues.append(f"{asset}/{tf}: data may be stale")
            except FileNotFoundError:
                issues.append(f"{asset}/{tf}: not cached")
            except Exception as e:
                issues.append(f"{asset}/{tf}: {e}")
    
    if issues:
        logger.warning("Data integrity issues found:")
        for issue in issues:
            logger.warning(f"  - {issue}")
    else:
        logger.info("All data checks passed!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare historical trading data")
    parser.add_argument("--tf", "--timeframe", default="M15", help="Timeframe (M15, H1, H4)")
    parser.add_argument("--bars", type=int, default=5000, help="Number of bars to download")
    parser.add_argument("--multi", action="store_true", help="Download multiple timeframes")
    parser.add_argument("--force", action="store_true", help="Force re-download (clear cache)")
    parser.add_argument("--check", action="store_true", help="Check data integrity only")
    
    args = parser.parse_args()
    
    if args.check:
        check_data_integrity()
    elif args.multi:
        download_multi_timeframe(args.bars, args.force)
    else:
        download_all(args.tf, args.bars, args.force)