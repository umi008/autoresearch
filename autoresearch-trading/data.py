# ═══════════════════════════════════════════════════════════════════════════════
# data.py — Data Layer
# OHLCV download, normalization and caching.
# MT5 only (Forex/Gold).
# ═══════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

import pandas as pd
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

# ─── Paths ─────────────────────────────────────────────────────────────────────
CACHE_DIR = Path.home() / '.cache' / 'autoresearch-trading'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ─── Constants ─────────────────────────────────────────────────────────────────
FOREX_ASSETS = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCHF', 'XAUUSD']

MT5_TIMEFRAMES = {
    'M1': 1,
    'M5': 5,
    'M15': 15,
    'M30': 30,
    'H1': 60,
    'H4': 240,
    'D1': 1440,
}

# ─── MT5 helpers ────────────────────────────────────────────────────────────────
@contextmanager
def mt5_context() -> Iterator:
    '''Initialize MT5 connection, yield, then shutdown.'''
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(f'MT5 initialize() failed: {mt5.last_error()}')
    try:
        yield mt5
    finally:
        mt5.shutdown()


def _parse_mt5_rates(rates: list, asset: str, timeframe: str) -> pd.DataFrame:
    '''Convert MT5 rates tuple-list to standardized DataFrame.'''
    if rates is None or (hasattr(rates, '__len__') and len(rates) == 0):
        return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'asset', 'timeframe'])
    df = pd.DataFrame(rates, columns=['timestamp', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
    df['volume'] = df['real_volume']
    df['asset'] = asset
    df['timeframe'] = timeframe
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'asset', 'timeframe']]
    return df


# ─── Public API ────────────────────────────────────────────────────────────────
def get_ohlcv(asset: str, timeframe: str, bars: int) -> pd.DataFrame:
    '''
    Download OHLCV for a single asset.
    Tries cache first (parquet), then fetches from MT5.
    '''
    safe_asset = asset.replace('/', '_')
    cache_file = CACHE_DIR / f'{safe_asset}_{timeframe}_{bars}.parquet'
    
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    if cache_file.exists():
        logger.debug(f'Cache hit: {cache_file.name}')
        return pd.read_parquet(cache_file)
    
    logger.info(f'Fetching {bars} bars of {timeframe} for {asset}')
    
    df = _fetch_mt5(asset, timeframe, bars)
    
    df.to_parquet(cache_file, index=False)
    logger.info(f'Cached to {cache_file.name} ({len(df)} rows)')
    return df


def _fetch_mt5(asset: str, timeframe: str, bars: int) -> pd.DataFrame:
    '''Fetch from MT5.'''
    import MetaTrader5 as mt5
    
    tf_code = MT5_TIMEFRAMES.get(timeframe, 15)
    
    with mt5_context() as mt5:
        rates = mt5.copy_rates_from_pos(asset, tf_code, 0, bars)
        if rates is None:
            logger.warning(f'MT5 returned None for {asset}, retrying...')
            time.sleep(1)
            rates = mt5.copy_rates_from_pos(asset, tf_code, 0, bars)
            if rates is None:
                raise RuntimeError(f'MT5 fetch failed for {asset}: {mt5.last_error()}')
    
    return _parse_mt5_rates(rates, asset, timeframe)


def get_multi_asset_data(assets: list[str], timeframe: str, bars: int) -> dict[str, pd.DataFrame]:
    '''Download OHLCV for multiple assets.'''
    result = {}
    for asset in assets:
        try:
            result[asset] = get_ohlcv(asset, timeframe, bars)
        except Exception as e:
            logger.error(f'Failed to fetch {asset}: {e}')
            continue
    return result


def get_latest_bar(asset: str) -> pd.Series:
    '''Get the most recent bar for an asset.'''
    df = get_ohlcv(asset, 'M15', 1)
    if df.empty:
        raise RuntimeError(f'No data for {asset}')
    return df.iloc[-1]


def is_market_open(asset: str) -> bool:
    '''Check if market is open for the given asset.'''
    now = datetime.now(timezone.utc)
    
    if asset in FOREX_ASSETS or asset == 'XAUUSD':
        # Forex/Gold closed on weekends
        if now.weekday() >= 5:
            return False
        return True
    
    return False


def clear_cache() -> None:
    '''
    Delete all cached .parquet files from CACHE_DIR.
    Useful when --force flag is used in prepare.py to force fresh data download.
    '''
    if not CACHE_DIR.exists():
        logger.debug('Cache dir does not exist, nothing to clear')
        return
    
    parquet_files = list(CACHE_DIR.glob('*.parquet'))
    
    if not parquet_files:
        logger.debug('No cached parquet files found')
        return
    
    for f in parquet_files:
        f.unlink()
        logger.info(f'Cleared cache: {f.name}')
    
    logger.info(f'Cleared {len(parquet_files)} cached file(s)')