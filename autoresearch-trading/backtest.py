"""
Walk-Forward Validation backtest engine using vectorbt.
Fixed module — DO NOT modify.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd
import vectorbt as vbt
from loguru import logger

# ─── WFV Config ────────────────────────────────────────────────────────────────
WFV_TRAIN_BARS = int(os.getenv("WFV_TRAIN_BARS", 3000))
WFV_TEST_BARS = int(os.getenv("WFV_TEST_BARS", 1000))
WFV_STEP_BARS = int(os.getenv("WFV_STEP_BARS", 1000))
WFV_N_WINDOWS = int(os.getenv("WFV_N_WINDOWS", 6))

# ─── NamedTuple for window results ─────────────────────────────────────────────
class WindowResult(NamedTuple):
    window_id: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    sharpe_oos: float
    max_drawdown: float
    total_trades: int
    win_rate: float
    profit_factor: float


def generate_walk_forward_windows(total_bars: int) -> list[tuple[int, int, int, int]]:
    """
    Generate (train_start, train_end, test_start, test_end) indices for each window.
    Windows are chronologically ordered, test segments do not overlap.
    """
    windows = []
    for i in range(WFV_N_WINDOWS):
        train_start = i * WFV_STEP_BARS
        train_end = train_start + WFV_TRAIN_BARS
        test_start = train_end
        test_end = test_start + WFV_TEST_BARS
        if test_end > total_bars:
            break
        windows.append((train_start, train_end, test_start, test_end))
    return windows


def run_single_window(
    df_asset: pd.DataFrame,
    strategy_module,
    train_start: int,
    train_end: int,
    test_start: int,
    test_end: int,
) -> dict:
    """
    Run strategy on TEST segment of a single window.
    Returns OOS metrics.
    """
    df_test = df_asset.iloc[test_start:test_end].copy()
    signals = strategy_module.generate_signals(df_test)
    
    entries = signals == 1
    exits = signals == -1
    
    portfolio = vbt.Portfolio.from_signals(
        close=df_test["close"],
        entries=entries,
        exits=exits,
        init_cash=10_000,
        fees=0.0002,
        slippage=0.0001,
        freq="15m",
    )
    
    stats = portfolio.stats()
    
    sharpe = float(stats.get("Sharpe Ratio", 0.0) or 0.0)
    max_dd = float(abs(stats.get("Max Drawdown [%]", 0.0) or 0.0)) / 100.0
    n_trades = int(stats.get("Total Trades", 0) or 0)
    win_rate = float(stats.get("Win Rate [%]", 0.0) or 0.0) / 100.0
    
    gross_profit = float(stats.get("Gross Profit [$]", 0.0) or 0.0)
    gross_loss = abs(float(stats.get("Gross Loss [$]", 1.0) or 1.0))
    pf = gross_profit / gross_loss if gross_loss > 0 else 0.0
    
    return {
        "sharpe_oos": sharpe,
        "max_drawdown": max_dd,
        "total_trades": n_trades,
        "win_rate": win_rate,
        "profit_factor": pf,
    }


def run_walk_forward_backtest(strategy_module, data: dict[str, pd.DataFrame]) -> dict:
    """
    Execute Walk-Forward Validation across all assets.
    Primary metric: sharpe_wfv = mean(sharpes_oos) - 0.5 * std(sharpes_oos)
    """
    all_window_sharpes: list[float] = []
    all_window_results: list[WindowResult] = []
    per_asset_wfv: dict[str, float] = {}
    
    for asset, df in data.items():
        total_bars = len(df)
        windows = generate_walk_forward_windows(total_bars)
        
        if not windows:
            min_required = WFV_TRAIN_BARS + WFV_TEST_BARS
            logger.warning(
                f"No valid windows for {asset}: got {total_bars} bars, "
                f"need >= {min_required} bars for 1 window "
                f"(train={WFV_TRAIN_BARS} + test={WFV_TEST_BARS}), "
                f"or {WFV_TRAIN_BARS + WFV_TEST_BARS + (WFV_N_WINDOWS - 1) * WFV_STEP_BARS} for {WFV_N_WINDOWS} windows"
            )
            continue
        
        asset_sharpes = []
        for i, (tr_s, tr_e, te_s, te_e) in enumerate(windows):
            result = run_single_window(
                df_asset=df,
                strategy_module=strategy_module,
                train_start=tr_s,
                train_end=tr_e,
                test_start=te_s,
                test_end=te_e,
            )
            asset_sharpes.append(result["sharpe_oos"])
            all_window_sharpes.append(result["sharpe_oos"])
            all_window_results.append(WindowResult(
                window_id=i,
                train_start=tr_s,
                train_end=tr_e,
                test_start=te_s,
                test_end=te_e,
                **result,
            ))
        
        # Per-asset WFV: mean - 0.5 * std (stability penalty)
        per_asset_wfv[asset] = (
            float(np.mean(asset_sharpes)) - 0.5 * float(np.std(asset_sharpes))
        )
    
    if not all_window_sharpes:
        return {"is_valid": False, "rejection_reason": "No valid windows generated"}
    
    sharpe_mean = float(np.mean(all_window_sharpes))
    sharpe_std = float(np.std(all_window_sharpes))
    sharpe_wfv = sharpe_mean - 0.5 * sharpe_std
    
    avg_dd = float(np.mean([r.max_drawdown for r in all_window_results]))
    total_trades = int(np.sum([r.total_trades for r in all_window_results]))
    avg_wr = float(np.mean([r.win_rate for r in all_window_results]))
    avg_pf = float(np.mean([r.profit_factor for r in all_window_results]))
    
    # Validation constraints
    is_valid = True
    rejection_reason = None
    
    if sharpe_wfv < 0:
        is_valid = False
        rejection_reason = f"sharpe_wfv={sharpe_wfv:.3f} < 0"
    elif avg_dd >= 0.15:
        is_valid = False
        rejection_reason = f"avg_max_drawdown={avg_dd:.3f} >= 0.15"
    elif total_trades < 200:
        is_valid = False
        rejection_reason = f"total_trades={total_trades} < 200"
    
    return {
        "sharpe_wfv": sharpe_wfv,
        "sharpe_mean_oos": sharpe_mean,
        "sharpe_std_oos": sharpe_std,
        "n_windows": len(all_window_sharpes),
        "avg_max_drawdown": avg_dd,
        "total_trades": total_trades,
        "avg_win_rate": avg_wr,
        "avg_profit_factor": avg_pf,
        "per_asset_wfv": per_asset_wfv,
        "window_sharpes": all_window_sharpes,
        "is_valid": is_valid,
        "rejection_reason": rejection_reason,
    }


def _load_strategy_module(strategy_path: str = "strategy.py"):
    """Dynamically load strategy module."""
    spec = importlib.util.spec_from_file_location("strategy", strategy_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _compute_hash(strategy_code: str) -> str:
    """Compute short hash of strategy code."""
    return hashlib.sha256(strategy_code.encode()).hexdigest()[:8]


if __name__ == "__main__":
    import data
    
    logger.info("Running quick backtest smoke test...")
    assets = ["EURUSD", "BTC/USDT"]
    data_dict = data.get_multi_asset_data(assets, "M15", 5000)
    
    strategy = _load_strategy_module()
    results = run_walk_forward_backtest(strategy, data_dict)
    
    print(json.dumps(results, indent=2, default=str))
