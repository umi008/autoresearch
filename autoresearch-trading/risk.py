'''
Risk management layer — pre-execution validations.
Fixed module — DO NOT modify.
'''

from __future__ import annotations

import os
from datetime import datetime, time, timezone
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# ─── Limits ────────────────────────────────────────────────────────────────────
MAX_POSITION_PCT = float(os.getenv('MAX_POSITION_PCT', 0.05))  # 5% of capital
MAX_LOSS_PCT = float(os.getenv('MAX_LOSS_PCT', 0.02))  # 2% per trade
MAX_DAILY_LOSS_PCT = float(os.getenv('MAX_DAILY_LOSS_PCT', 0.02))  # 2% daily
MAX_CORRELATION = float(os.getenv('MAX_CORRELATION', 0.7))  # max correlation between positions

# ─── High-impact news hours (UTC) ─────────────────────────────────────────────
HIGH_IMPACT_NEWS = {
    'EURUSD': [(time(14, 30), time(15, 0))],  # US NFP, CPI, FOMC
    'GBPUSD': [(time(14, 30), time(15, 0))],
    'USDJPY': [(time(3, 30), time(4, 0))],   # JPY decisions
    'XAUUSD': [(time(14, 30), time(15, 0))],
}

# ─── Correlation groups (assets that move together) ─────────────────────────────
CORRELATION_GROUPS = {
    'EUR': ['EURUSD', 'EURGBP', 'EURJPY', 'EURAUD'],
    'USD': ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF'],
    'METALS': ['XAUUSD', 'XAGUSD'],
    'CRYPTO': ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'],
}


class RiskError(Exception):
    '''Raised when a risk check fails.'''
    pass


def validate_position_size(
    position_size: float,
    capital: float,
    price: float,
    asset: str,
) -> bool:
    '''
    Validate position size does not exceed MAX_POSITION_PCT of capital.
    '''
    position_value = position_size * price
    pct = position_value / capital
    
    if pct > MAX_POSITION_PCT:
        logger.warning(
            f'Position size rejected: {pct:.2%} of capital '
            f'(max={MAX_POSITION_PCT:.2%})'
        )
        return False
    return True


def validate_stop_loss(
    entry_price: float,
    stop_loss: float,
    capital: float,
    position_size: float,
) -> bool:
    '''
    Validate stop loss does not exceed MAX_LOSS_PCT per trade.
    '''
    if stop_loss <= 0 or entry_price <= 0:
        return False
    
    loss_per_unit = abs(entry_price - stop_loss)
    total_loss = loss_per_unit * position_size
    pct = total_loss / capital
    
    if pct > MAX_LOSS_PCT:
        logger.warning(
            f'Stop loss rejected: {pct:.2%} of capital '
            f'(max={MAX_LOSS_PCT:.2%})'
        )
        return False
    return True


def check_daily_loss(current_pnl: float, capital: float) -> bool:
    '''
    Check if daily P&L loss exceeds MAX_DAILY_LOSS_PCT (circuit breaker).
    Alias for validate_daily_loss for compatibility.
    '''
    if capital <= 0:
        return True
    
    daily_return = current_pnl / capital
    
    if daily_return <= -MAX_DAILY_LOSS_PCT:
        logger.error(
            f'DAILY LOSS CIRCUIT BREAKER: {daily_return:.2%} '
            f'(limit={-MAX_DAILY_LOSS_PCT:.2%})'
        )
        return False
    return True


def validate_daily_loss(current_pnl: float, capital: float) -> bool:
    '''
    Check if daily P&L loss exceeds MAX_DAILY_LOSS_PCT (circuit breaker).
    '''
    return check_daily_loss(current_pnl, capital)


def is_news_time(asset: str, timestamp: Optional[datetime] = None) -> bool:
    '''
    Check if current time is a high-impact news window for the asset.
    This is a simplified check — production would use a news API.
    '''
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    
    windows = HIGH_IMPACT_NEWS.get(asset, [])
    current_time = timestamp.time()
    
    for start, end in windows:
        if start <= current_time <= end:
            logger.warning(f'High-impact news window for {asset}, skipping execution')
            return True
    
    return False


def check_correlation(
    new_asset: str,
    open_positions: list,
    prices: dict[str, float],
) -> bool:
    '''
    Check if new asset is too correlated with existing positions.
    Returns True if correlation is acceptable, False if it should be rejected.
    '''
    if not open_positions or new_asset not in prices:
        return True
    
    # Find correlation group for new asset
    new_group = None
    for group_name, assets in CORRELATION_GROUPS.items():
        if new_asset in assets:
            new_group = group_name
            break
    
    if new_group is None:
        return True
    
    # Count existing positions in same group
    same_group_count = 0
    for pos in open_positions:
        for group_name, assets in CORRELATION_GROUPS.items():
            if pos.symbol in assets and group_name == new_group:
                same_group_count += 1
                break
    
    # If we already have positions in this group, reject new one
    if same_group_count > 0:
        logger.warning(
            f'Correlation check failed: {new_asset} in group {new_group} '
            f'but already have {same_group_count} position(s) in that group'
        )
        return False
    
    return True


def validate_order(
    asset: str,
    side: str,
    position_size: float,
    entry_price: float,
    stop_loss: float,
    capital: float,
    current_pnl: float,
    open_positions: list,
    prices: dict[str, float],
    timestamp: Optional[datetime] = None,
) -> bool:
    '''
    Run all pre-execution risk checks (circuit breakers).
    Returns True if all checks pass, raises RiskError otherwise.
    '''
    try:
        # Position size check
        if not validate_position_size(position_size, capital, entry_price, asset):
            raise RiskError(f'Position size exceeds {MAX_POSITION_PCT:.2%}')
        
        # Stop loss check
        if stop_loss > 0:
            if not validate_stop_loss(entry_price, stop_loss, capital, position_size):
                raise RiskError(f'Stop loss exceeds {MAX_LOSS_PCT:.2%}')
        
        # Daily loss circuit breaker
        if not check_daily_loss(current_pnl, capital):
            raise RiskError(f'Daily loss limit {MAX_DAILY_LOSS_PCT:.2%} reached')
        
        # News filter
        if is_news_time(asset, timestamp):
            raise RiskError('High-impact news window')
        
        # Correlation check
        if not check_correlation(asset, open_positions, prices):
            raise RiskError(f'Correlation limit ({MAX_CORRELATION}) exceeded')
        
        return True
    
    except RiskError:
        raise
    except Exception as e:
        logger.error(f'Risk check error: {e}')
        raise RiskError(f'Risk check failed: {e}')


def emergency_close_all() -> dict:
    '''
    Emergency close all positions across all brokers.
    Returns dict with results for each broker.
    '''
    from execute import close_position, get_positions
    
    results = {'mt5': [], 'ccxt': [], 'errors': []}
    
    try:
        positions = get_positions()
        
        for pos in positions:
            try:
                is_crypto = '/' in pos.symbol
                result = close_position(
                    ticket_or_symbol=pos.order_id or pos.symbol,
                    volume=pos.size,
                    is_crypto=is_crypto,
                )
                
                if is_crypto:
                    results['ccxt'].append({
                        'symbol': pos.symbol,
                        'result': result.status,
                    })
                else:
                    results['mt5'].append({
                        'symbol': pos.symbol,
                        'result': result.status,
                    })
            except Exception as e:
                results['errors'].append({
                    'symbol': pos.symbol,
                    'error': str(e),
                })
        
        logger.warning(f'Emergency close completed: {len(positions)} positions closed')
    
    except Exception as e:
        logger.error(f'Emergency close failed: {e}')
        results['errors'].append({'error': str(e)})
    
    return results


def pre_execution_check(
    asset: str,
    position_size: float,
    entry_price: float,
    stop_loss: float,
    capital: float,
    current_pnl: float,
    timestamp: Optional[datetime] = None,
) -> bool:
    '''
    Run all pre-execution risk checks.
    Returns True if all checks pass, raises RiskError otherwise.
    Deprecated: use validate_order instead.
    '''
    return validate_order(
        asset=asset,
        side='long',  # not used in current checks
        position_size=position_size,
        entry_price=entry_price,
        stop_loss=stop_loss,
        capital=capital,
        current_pnl=current_pnl,
        open_positions=[],
        prices={},
        timestamp=timestamp,
    )