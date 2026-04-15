"""
Common utilities/helpers.
"""

from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ─── Path helpers ──────────────────────────────────────────────────────────────
def get_project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).parent


def ensure_dir(path: Path | str) -> Path:
    """Ensure directory exists."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


# ─── Date/time helpers ─────────────────────────────────────────────────────────
def now_iso() -> str:
    """Get current UTC datetime as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def parse_timeframe(tf: str) -> int:
    """Parse timeframe string to minutes."""
    mapping = {
        "M1": 1,
        "M5": 5,
        "M15": 15,
        "M30": 30,
        "H1": 60,
        "H4": 240,
        "D1": 1440,
    }
    return mapping.get(tf, 15)


# ─── Hashing ────────────────────────────────────────────────────────────────────
def short_hash(text: str) -> str:
    """Return 8-char SHA256 hash."""
    return hashlib.sha256(text.encode()).hexdigest()[:8]


# ─── Number formatting ─────────────────────────────────────────────────────────
def format_pct(value: float) -> str:
    """Format as percentage string."""
    return f"{value:.2%}"


def format_price(value: float, decimals: int = 5) -> str:
    """Format price with appropriate decimals."""
    if value >= 1000:
        decimals = 2
    elif value >= 1:
        decimals = 4
    return f"{value:.{decimals}f}"


# ─── DataFrame helpers ─────────────────────────────────────────────────────────
def dropna_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with NaN in OHLCV columns."""
    return df.dropna(subset=["open", "high", "low", "close"])


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Resample OHLCV data to different timeframe."""
    tf_map = {
        "M1": "1T",
        "M5": "5T",
        "M15": "15T",
        "M30": "30T",
        "H1": "1H",
        "H4": "4H",
        "D1": "1D",
    }
    
    freq = tf_map.get(timeframe, "15T")
    
    resampled = df.set_index("timestamp").resample(freq).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    })
    
    resampled["asset"] = df["asset"].iloc[0]
    resampled["timeframe"] = timeframe
    
    return resampled.reset_index()


# ─── Logging helpers ────────────────────────────────────────────────────────────
def setup_logging(log_dir: Path | str = "logs", rotation: str = "00:00") -> None:
    """Configure loguru logging."""
    from loguru import logger
    
    log_dir = Path(log_dir)
    ensure_dir(log_dir)
    
    logger.add(
        log_dir / f"autoresearch_{datetime.now(timezone.utc):%Y%m%d}.log",
        rotation=rotation,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        level="INFO",
    )
    
    # Also print to stdout
    logger.add(sys.stdout, format="{time:HH:mm:ss} | {level} | {message}")


# ─── Validation helpers ─────────────────────────────────────────────────────────
def validate_ohlcv(df: pd.DataFrame) -> bool:
    """Validate OHLCV DataFrame has required columns and valid data."""
    required = ["timestamp", "open", "high", "low", "close", "volume", "asset", "timeframe"]
    
    for col in required:
        if col not in df.columns:
            return False
    
    if df.empty:
        return False
    
    # Check high >= low
    if not (df["high"] >= df["low"]).all():
        return False
    
    # Check high >= open, close
    if not ((df["high"] >= df["open"]) & (df["high"] >= df["close"])).all():
        return False
    
    # Check low <= open, close
    if not ((df["low"] <= df["open"]) & (df["low"] <= df["close"])).all():
        return False
    
    return True


# ─── JSON helpers ──────────────────────────────────────────────────────────────
def to_json_serializable(obj: Any) -> Any:
    """Convert numpy/pandas types to JSON-serializable Python types."""
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Series):
        return obj.to_dict()
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {k: to_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_json_serializable(i) for i in obj]
    return obj


# ─── Math helpers ──────────────────────────────────────────────────────────────
def nanmean(arr: list[float]) -> float:
    """Mean ignoring NaN values."""
    cleaned = [x for x in arr if x is not None and not np.isnan(x)]
    return float(np.mean(cleaned)) if cleaned else 0.0


def nanstd(arr: list[float]) -> float:
    """Std ignoring NaN values."""
    cleaned = [x for x in arr if x is not None and not np.isnan(x)]
    return float(np.std(cleaned)) if cleaned else 0.0
