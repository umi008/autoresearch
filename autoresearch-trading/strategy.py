"""
Strategy v1 — baseline
EMA crossover + RSI filter with ATR-based stop loss and take profit.
"""

import pandas as pd
import pandas_ta as ta

# ─── PARAMS ────────────────────────────────────────────────────────────────────
PARAMS = {
    "ema_fast": 9,
    "ema_slow": 21,
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "atr_period": 14,
    "sl_atr_mult": 1.5,
    "tp_atr_mult": 2.5,
    "position_size_pct": 0.02,
}


def generate_signals(df: pd.DataFrame) -> pd.Series:
    """
    Generate trading signals from OHLCV data.
    
    Args:
        df: DataFrame with columns [open, high, low, close, volume]
    
    Returns:
        pd.Series with values:
          1  = long signal
         -1  = short signal
          0  = flat/no signal
    """
    close = df["close"]
    
    # Indicators
    ema_fast = ta.ema(close, length=PARAMS["ema_fast"])
    ema_slow = ta.ema(close, length=PARAMS["ema_slow"])
    rsi = ta.rsi(close, length=PARAMS["rsi_period"])
    
    signal = pd.Series(0, index=df.index)
    
    # Long: fast EMA crosses above slow EMA AND RSI not overbought
    long_cond = (ema_fast > ema_slow) & (rsi < PARAMS["rsi_overbought"])
    signal[long_cond] = 1
    
    # Short: fast EMA crosses below slow EMA AND RSI not oversold
    short_cond = (ema_fast < ema_slow) & (rsi > PARAMS["rsi_oversold"])
    signal[short_cond] = -1
    
    return signal


def get_position_size(capital: float, price: float, atr: float) -> float:
    """
    Calculate position size based on ATR volatility.
    
    Args:
        capital: Account capital
        price: Current asset price
        atr: Average True Range value
    
    Returns:
        Number of units to buy/sell
    """
    risk_amount = capital * PARAMS["position_size_pct"]
    sl_distance = atr * PARAMS["sl_atr_mult"]
    
    if sl_distance <= 0:
        return 0.0
    
    return risk_amount / sl_distance


def get_atr(df: pd.DataFrame) -> pd.Series:
    """Calculate ATR for the given DataFrame."""
    return ta.atr(df["high"], df["low"], df["close"], length=PARAMS["atr_period"])
