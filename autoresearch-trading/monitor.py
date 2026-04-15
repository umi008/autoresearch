'''
Real-time monitoring with logging alerts.
Fixed module — DO NOT modify.
'''

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# ─── Live readiness thresholds ──────────────────────────────────────────────────
MIN_EXPERIMENTS_FOR_LIVE = int(os.getenv('MIN_EXPERIMENTS_FOR_LIVE', 50))
MIN_SHARPE_FOR_LIVE = float(os.getenv('MIN_SHARPE_FOR_LIVE', 1.0))
MAX_DRAWDOWN_FOR_LIVE = float(os.getenv('MAX_DRAWDOWN_FOR_LIVE', 0.10))


# ─── Metrics Tracker ───────────────────────────────────────────────────────────
@dataclass
class TradingMetrics:
    '''Current trading session metrics.'''
    experiment_count: int = 0
    best_sharpe_wfv: float = 0.0
    current_sharpe_wfv: float = 0.0
    current_drawdown: float = 0.0
    current_pnl: float = 0.0
    trades_today: int = 0
    sharpe_mobile: float = 0.0
    consecutive_losses: int = 0
    is_running: bool = False


class Monitor:
    '''Real-time metrics tracker with logging alerts.'''
    
    def __init__(self, db_path: str = 'experiments.db'):
        self.db_path = db_path
        self.metrics = TradingMetrics()
        self._lock = threading.Lock()
        self._start_time = datetime.now(timezone.utc)
    
    def update_metrics(self, **kwargs) -> None:
        '''Update any metric.'''
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self.metrics, key):
                    setattr(self.metrics, key, value)
    
    def increment(self, key: str, amount: int = 1) -> None:
        '''Increment a counter metric.'''
        with self._lock:
            if hasattr(self.metrics, key):
                setattr(self.metrics, getattr(self.metrics, key) + amount)
    
    def record_experiment(self, sharpe_wfv: float, is_valid: bool) -> None:
        '''Record an experiment result.'''
        self.increment('experiment_count')
        self.update_metrics(current_sharpe_wfv=sharpe_wfv)
        
        if is_valid and sharpe_wfv > self.metrics.best_sharpe_wfv:
            self.update_metrics(best_sharpe_wfv=sharpe_wfv)
        
        # Alert if sharpe_wfv < 0 for 5 consecutive experiments
        if sharpe_wfv < 0:
            self.increment('consecutive_losses')
            if self.metrics.consecutive_losses >= 5:
                logger.error(
                    f'CRITICAL: Sharpe negativo por {self.metrics.consecutive_losses} '
                    f'experimentos seguidos'
                )
        else:
            self.update_metrics(consecutive_losses=0)
    
    def check_drawdown_alert(self) -> None:
        '''Alert if drawdown exceeds 12%.'''
        if self.metrics.current_drawdown >= 0.12:
            logger.error(
                f'DRAWDOWN ALERTA: {self.metrics.current_drawdown:.2%} '
                f'(limite: 12%)'
            )
    
    def report_every_n_experiments(self, n: int = 10) -> None:
        '''Log summary report every N experiments.'''
        if self.metrics.experiment_count % n == 0 and self.metrics.experiment_count > 0:
            self._log_summary()
    
    def _log_summary(self) -> None:
        '''Log experiment summary.'''
        m = self.metrics
        is_ready = self.is_ready_for_live()
        ready_status = 'READY' if is_ready else 'NOT READY'
        
        logger.info(
            f'Experiment summary: #{m.experiment_count} | '
            f'Best Sharpe WFV: {m.best_sharpe_wfv:.3f} | '
            f'Current Sharpe: {m.current_sharpe_wfv:.3f} | '
            f'Drawdown: {m.current_drawdown:.2%} | '
            f'P&L: ${m.current_pnl:.2f} | '
            f'Status: {ready_status}'
        )
    
    def get_metrics(self) -> TradingMetrics:
        '''Get a copy of current metrics.'''
        with self._lock:
            return TradingMetrics(**vars(self.metrics))
    
    def get_status_text(self) -> str:
        '''Get formatted status text.'''
        m = self.metrics
        elapsed = datetime.now(timezone.utc) - self._start_time
        hours = elapsed.total_seconds() / 3600
        
        is_ready = self.is_ready_for_live()
        ready_status = 'READY FOR LIVE' if is_ready else 'NOT READY'
        
        lines = [
            '=== AUTORESEARCH STATUS ===',
            f'Time running: {hours:.1f}h',
            f'Experiments: {m.experiment_count}',
            f'Best Sharpe WFV: {m.best_sharpe_wfv:.3f}',
            f'Current Sharpe: {m.current_sharpe_wfv:.3f}',
            f'P&L: ${m.current_pnl:.2f}',
            f'Drawdown: {m.current_drawdown:.2%}',
            f'Consecutive losses: {m.consecutive_losses}',
            f'Status: {ready_status}',
        ]
        
        return '\n'.join(lines)
    
    def is_ready_for_live(self) -> bool:
        '''
        Check if system is ready to transition to live trading.
        Criteria:
        - At least MIN_EXPERIMENTS_FOR_LIVE experiments completed
        - Best Sharpe WFV >= MIN_SHARPE_FOR_LIVE
        - Current drawdown < MAX_DRAWDOWN_FOR_LIVE
        - No more than 3 consecutive losses
        '''
        m = self.metrics
        
        if m.experiment_count < MIN_EXPERIMENTS_FOR_LIVE:
            logger.info(f'Not ready for live: only {m.experiment_count} experiments (need {MIN_EXPERIMENTS_FOR_LIVE})')
            return False
        
        if m.best_sharpe_wfv < MIN_SHARPE_FOR_LIVE:
            logger.info(f'Not ready for live: Sharpe {m.best_sharpe_wfv:.3f} < {MIN_SHARPE_FOR_LIVE}')
            return False
        
        if m.current_drawdown >= MAX_DRAWDOWN_FOR_LIVE:
            logger.info(f'Not ready for live: Drawdown {m.current_drawdown:.2%} >= {MAX_DRAWDOWN_FOR_LIVE}')
            return False
        
        if m.consecutive_losses > 3:
            logger.info(f'Not ready for live: {m.consecutive_losses} consecutive losses')
            return False
        
        return True


def init_db(db_path: str = 'experiments.db') -> None:
    '''Initialize SQLite database with required tables.'''
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id TEXT UNIQUE NOT NULL,
            timestamp TEXT NOT NULL,
            sharpe_wfv REAL,
            sharpe_mean_oos REAL,
            sharpe_std_oos REAL,
            avg_max_drawdown REAL,
            total_trades INTEGER,
            avg_win_rate REAL,
            avg_profit_factor REAL,
            is_valid BOOLEAN,
            rejection_reason TEXT,
            strategy_hash TEXT,
            description TEXT,
            status TEXT CHECK(status IN ('keep', 'discard', 'crash')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS window_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id TEXT NOT NULL,
            asset TEXT NOT NULL,
            window_id INTEGER NOT NULL,
            train_start INTEGER,
            train_end INTEGER,
            test_start INTEGER,
            test_end INTEGER,
            sharpe_oos REAL,
            max_drawdown REAL,
            total_trades INTEGER,
            win_rate REAL,
            profit_factor REAL,
            FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info(f'Database initialized: {db_path}')


def log_experiment(
    db_path: str,
    experiment_id: str,
    metrics: dict,
    strategy_hash: str,
    description: str,
    status: str,
) -> None:
    '''Insert experiment record into database.'''
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO experiments (
            experiment_id, timestamp, sharpe_wfv, sharpe_mean_oos, sharpe_std_oos,
            avg_max_drawdown, total_trades, avg_win_rate, avg_profit_factor,
            is_valid, rejection_reason, strategy_hash, description, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        experiment_id,
        datetime.now(timezone.utc).isoformat(),
        metrics.get('sharpe_wfv'),
        metrics.get('sharpe_mean_oos'),
        metrics.get('sharpe_std_oos'),
        metrics.get('avg_max_drawdown'),
        metrics.get('total_trades'),
        metrics.get('avg_win_rate'),
        metrics.get('avg_profit_factor'),
        metrics.get('is_valid'),
        metrics.get('rejection_reason'),
        strategy_hash,
        description,
        status,
    ))
    
    conn.commit()
    conn.close()


def get_last_experiments(db_path: str, n: int = 10) -> pd.DataFrame:
    '''Get last N experiments from database.'''
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        f'SELECT * FROM experiments ORDER BY id DESC LIMIT {n}',
        conn
    )
    conn.close()
    return df


# Singleton instance
_monitor: Optional[Monitor] = None


def get_monitor() -> Monitor:
    '''Get or create singleton Monitor instance.'''
    global _monitor
    if _monitor is None:
        _monitor = Monitor()
    return _monitor