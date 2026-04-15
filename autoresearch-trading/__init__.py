"""
Autoresearch Trading System
===========================

LLM-driven autonomous trading strategy researcher.
Uses Walk-Forward Validation with vectorbt.

## Quick Start

1. Install dependencies:
   uv pip install -e .

2. Copy and configure .env:
   cp .env.example .env
   # Edit .env with your credentials

3. Prepare historical data:
   uv run python prepare.py --multi --force

4. Run the agent:
   uv run python agent.py

## Project Structure

- `agent.py`      — Main loop (LLM → strategy → backtest → compare → log)
- `strategy.py`   — Trading strategy (modified by agent)
- `backtest.py`   — Walk-Forward Validation engine (fixed)
- `data.py`       — OHLCV data layer (MT5 + CCXT)
- `execute.py`    — Execution bridge (MT5 + CCXT)
- `risk.py`       — Pre-execution risk checks
- `monitor.py`    — Real-time metrics + Telegram alerts
- `prepare.py`    — Historical data download script
- `utils.py`      — Common helpers

## Metrics

Primary metric: sharpe_wfv = mean(sharpes_oos) - 0.5 * std(sharpes_oos)

Constraints:
- sharpe_wfv >= 0
- avg_max_drawdown < 0.15
- total_trades >= 200
"""

__version__ = "0.1.0"
