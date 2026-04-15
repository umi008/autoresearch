'''
Execution layer — bridge to MT5 only.
Forex and Gold trading only.
Fixed module — DO NOT modify.
'''

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# ─── Mode ─────────────────────────────────────────────────────────────────────
MODE = os.getenv('MODE', 'paper')

# ─── Order types ───────────────────────────────────────────────────────────────
class OrderSide(Enum):
    BUY = 'buy'
    SELL = 'sell'


class OrderType(Enum):
    MARKET = 'market'
    LIMIT = 'limit'
    STOP = 'stop'


@dataclass
class OrderResult:
    order_id: Optional[str]
    status: str  # 'filled', 'pending', 'rejected', 'error'
    filled_price: Optional[float]
    message: str


@dataclass
class Position:
    symbol: str
    side: str  # 'long' or 'short'
    size: float
    entry_price: float
    unrealized_pnl: float
    order_id: Optional[str] = None


@dataclass
class AccountBalance:
    equity: float
    margin: float
    free_margin: float
    unrealized_pnl: float
    currency: str = 'USD'


# ─── MT5 Execution ─────────────────────────────────────────────────────────────
def _init_mt5():
    '''Initialize MT5 connection.'''
    import MetaTrader5 as mt5
    
    if not mt5.initialize():
        raise RuntimeError(f'MT5 init failed: {mt5.last_error()}')
    
    login = int(os.getenv('MT5_LOGIN', 0))
    password = os.getenv('MT5_PASSWORD', '')
    server = os.getenv('MT5_SERVER', '')
    
    if login and password and server:
        if not mt5.login(login, password=password, server=server):
            raise RuntimeError(f'MT5 login failed: {mt5.last_error()}')
    
    return mt5


def place_order(
    symbol: str,
    side: OrderSide,
    volume: float,
    order_type: OrderType = OrderType.MARKET,
    price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
) -> OrderResult:
    '''
    Send order via MT5 (Forex/Gold only).
    '''
    return send_order_mt5(symbol, side, volume, order_type, price, stop_loss, take_profit)


def send_order_mt5(
    symbol: str,
    side: OrderSide,
    volume: float,
    order_type: OrderType = OrderType.MARKET,
    price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
) -> OrderResult:
    '''Send order to MT5.'''
    import MetaTrader5 as mt5
    
    mt5_conn = _init_mt5()
    try:
        order_type_code = {
            OrderType.MARKET: mt5.ORDER_MARKET,
            OrderType.LIMIT: mt5.ORDER_LIMIT,
            OrderType.STOP: mt5.ORDER_STOP,
        }[order_type]
        
        action = mt5.ORDER_TYPE_BUY if side == OrderSide.BUY else mt5.ORDER_TYPE_SELL
        
        request = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': symbol,
            'volume': volume,
            'type': action,
            'price': price if price else 0,
            'sl': stop_loss if stop_loss else 0,
            'tp': take_profit if take_profit else 0,
            'deviation': 10,
            'magic': 0,
            'comment': 'autoresearch',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5_conn.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return OrderResult(
                order_id=None,
                status='rejected',
                filled_price=None,
                message=f'MT5 retcode={result.retcode}',
            )
        
        return OrderResult(
            order_id=str(result.order),
            status='filled',
            filled_price=result.price,
            message='OK',
        )
    
    except Exception as e:
        return OrderResult(order_id=None, status='error', filled_price=None, message=str(e))
    finally:
        mt5.shutdown()


def get_account_balance() -> AccountBalance:
    '''Get account balance info from MT5.'''
    import MetaTrader5 as mt5
    
    mt5_conn = _init_mt5()
    try:
        info = mt5_conn.account_info()
        
        return AccountBalance(
            equity=info.equity,
            margin=info.margin,
            free_margin=info.margin_free,
            unrealized_pnl=info.profit,
            currency=info.currency or 'USD',
        )
    finally:
        mt5.shutdown()


def get_positions() -> list[Position]:
    '''Get open positions from MT5.'''
    import MetaTrader5 as mt5
    
    mt5_conn = _init_mt5()
    try:
        positions = mt5_conn.positions_get()
        result = []
        
        for p in positions:
            result.append(Position(
                symbol=p.symbol,
                side='long' if p.type == mt5.POSITION_TYPE_BUY else 'short',
                size=p.volume,
                entry_price=p.price_open,
                unrealized_pnl=p.profit,
                order_id=str(p.ticket),
            ))
        
        return result
    finally:
        mt5.shutdown()


def close_position(ticket: str, volume: Optional[float] = None) -> OrderResult:
    '''Close a specific MT5 position by ticket.'''
    import MetaTrader5 as mt5
    
    mt5_conn = _init_mt5()
    try:
        positions = mt5_conn.positions_get(ticket=int(ticket))
        if not positions:
            return OrderResult(None, 'error', None, 'Position not found')
        
        pos = positions[0]
        close_side = OrderSide.SELL if pos.type == mt5.POSITION_TYPE_BUY else OrderSide.BUY
        close_volume = volume if volume else pos.volume
        
        return send_order_mt5(
            symbol=pos.symbol,
            side=close_side,
            volume=close_volume,
        )
    finally:
        mt5.shutdown()


def close_all_positions() -> dict:
    '''Close all open MT5 positions.'''
    results = {'closed': [], 'errors': []}
    
    positions = get_positions()
    for pos in positions:
        try:
            result = close_position(ticket=pos.order_id, volume=pos.size)
            results['closed'].append({
                'symbol': pos.symbol,
                'status': result.status,
            })
        except Exception as e:
            results['errors'].append({
                'symbol': pos.symbol,
                'error': str(e),
            })
    
    return results