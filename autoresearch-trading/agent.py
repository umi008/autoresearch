# Autoresearch Trading Agent - Main Loop.
# Fixed module - DO NOT modify.
#
# Loop:
# 1. Read current strategy.py
# 2. Read last N experiments from experiments.db
# 3. Build prompt with program.md + strategy.py + history
# 4. Call LLM -> get new strategy.py
# 5. Write new strategy.py
# 6. Run backtest.py (walk-forward)
# 7. Compare sharpe_wfv with best so far
# 8. If improved -> save as best_strategy.py + log success
#    If not -> revert strategy.py + log discard
# 9. Sleep (GPU cooldown)
# 10. Repeat
# Supports --max-experiments N and --duration-hours H for bounded runs.

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import backtest
import data
import monitor
import utils
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# ─── LLM Config (OpenRouter only) ─────────────────────────────────────────────
LLM_TIMEOUT = int(os.getenv('LLM_TIMEOUT', 120))  # seconds
LLM_MODEL = os.getenv('LLM_MODEL', 'openai/gpt-oss-120b:free')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')

if not OPENROUTER_API_KEY:
    raise ValueError('OPENROUTER_API_KEY is required')

# ─── Agent Config ────────────────────────────────────────────────────────────────
EXPERIMENT_COOLDOWN = int(os.getenv('EXPERIMENT_COOLDOWN', 60))  # seconds
N_LAST_EXPERIMENTS = 10
ASSETS = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']  # Forex + Gold only
DEFAULT_BARS = 5000


def _get_llm_client():
    '''Get OpenAI-compatible LLM client (OpenRouter only).'''
    from openai import OpenAI
    
    client = OpenAI(
        base_url='https://openrouter.ai/api/v1',
        api_key=OPENROUTER_API_KEY,
    )
    
    return client


def _load_strategy_module(strategy_path: str = 'strategy.py'):
    '''Dynamically load strategy module.'''
    spec = importlib.util.spec_from_file_location('strategy', strategy_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _compute_hash(strategy_code: str) -> str:
    '''Compute short hash of strategy code.'''
    return hashlib.sha256(strategy_code.encode()).hexdigest()[:8]


def _read_file(path: str) -> str:
    '''Read file contents.'''
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _write_file(path: str, content: str) -> None:
    '''Write file contents.'''
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def _build_prompt(program_md: str, strategy_code: str, history: str) -> str:
    '''Build prompt for LLM.'''
    return f'''You are an expert trading strategy researcher. Your goal is to improve a trading strategy by modifying strategy.py.

## Current strategy.py
```python
{strategy_code}
```

## Recent experiment history
{history}

## Instructions from human (program.md)
{program_md}

## Task
Analyze the current strategy and history. Propose 1-2 specific modifications to improve the Sharpe WFV metric.
Return ONLY the complete new strategy.py code with your changes.

The strategy MUST:
- Keep the same structure (PARAMS dict, generate_signals(), get_position_size())
- Return 1 for long, -1 for short, 0 for flat signals
- Be executable Python with pandas and pandas-ta

Output ONLY the complete strategy.py code, no explanations.
'''


def _call_llm(prompt: str) -> str:
    '''Call LLM and return response with timeout.'''
    client = _get_llm_client()
    
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {'role': 'system', 'content': 'You are an expert trading researcher.'},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.7,
            max_tokens=4000,
            timeout=LLM_TIMEOUT,
        )
        msg = response.choices[0].message
        content = msg.content
        # Handle reasoning models (minimax-m1, deepseek-r1) that put text in reasoning
        if content is None and msg.reasoning:
            reasoning_text = msg.reasoning
            if isinstance(reasoning_text, str):
                content = reasoning_text
            elif hasattr(reasoning_text, 'reasoning_text'):
                content = str(reasoning_text.reasoning_text)
            elif isinstance(reasoning_text, list) and reasoning_text:
                # Sometimes reasoning_details contains the text
                for item in reasoning_text:
                    if hasattr(item, 'text'):
                        content = item.text
                        break
        if content is None:
            logger.error('LLM returned None content')
            return ''
        return content
    
    except Exception as e:
        logger.error(f'LLM call failed: {e}')
        raise


def _parse_llm_response(response: str) -> str:
    '''Extract Python code from LLM response, stripping markdown fences.'''
    if not response:
        return ''
    
    # Remove markdown code blocks if present
    if '```python' in response:
        response = response.split('```python')[1]
    elif '```' in response:
        parts = response.split('```')
        response = parts[1] if len(parts) > 1 else parts[0]
    
    # Remove triple-quoted docstrings that LLM might prepend
    if response.startswith('```'):
        response = response[3:]
    if response.endswith('```'):
        response = response[:-3]
    
    # Remove 'strategy.py' header or similar
    for prefix in ['strategy.py', 'python']:
        if response.startswith(prefix):
            response = response[len(prefix):]
    
    return response.strip()


def run_experiment(
    experiment_id: str,
    strategy_code: str,
    data_cache: dict[str, ...],
) -> dict:
    '''
    Run single experiment: backtest strategy code.
    Returns metrics dict.
    '''
    # Write temporary strategy file
    tmp_path = f'_tmp_strategy_{experiment_id}.py'
    _write_file(tmp_path, strategy_code)
    
    try:
        # Load and run backtest
        module = _load_strategy_module(tmp_path)
        metrics = backtest.run_walk_forward_backtest(module, data_cache)
        metrics['strategy_hash'] = _compute_hash(strategy_code)
        
        return metrics
    
    except SyntaxError as e:
        logger.error(f'Experiment {experiment_id} syntax error: {e}')
        return {
            'is_valid': False,
            'rejection_reason': f'syntax_error: {e}',
            'sharpe_wfv': 0.0,
        }
    except Exception as e:
        logger.error(f'Experiment {experiment_id} crashed: {e}')
        return {
            'is_valid': False,
            'rejection_reason': f'crash: {e}',
            'sharpe_wfv': 0.0,
        }
    
    finally:
        # Cleanup temp file
        Path(tmp_path).unlink(missing_ok=True)


class Agent:
    '''Main autoresearch agent loop.'''
    
    def __init__(
        self,
        strategy_path: str = 'strategy.py',
        program_path: str = 'program.md',
        db_path: str = 'experiments.db',
        best_path: str = 'best_strategy.py',
        max_experiments: Optional[int] = None,
        duration_hours: Optional[float] = None,
    ):
        self.strategy_path = strategy_path
        self.program_path = program_path
        self.db_path = db_path
        self.best_path = best_path
        self.max_experiments = max_experiments
        self.duration_hours = duration_hours
        
        # State
        self.best_sharpe = 0.0
        self.experiment_count = self._get_next_experiment_number()
        self.last_strategy = ''
        self.start_time = datetime.now(timezone.utc)
    
    def _get_next_experiment_number(self) -> int:
        '''Get next experiment number from database.'''
        if os.path.exists(self.db_path):
            try:
                import sqlite3
                conn = sqlite3.connect(self.db_path)
                cur = conn.cursor()
                cur.execute('SELECT MAX(CAST(SUBSTR(experiment_id, 5) AS INTEGER)) FROM experiments')
                row = cur.fetchone()
                conn.close()
                if row and row[0] is not None:
                    return row[0] + 1
            except Exception:
                pass
        return 0
    
    def _load_data(self) -> dict:
        '''Load data for all assets.'''
        logger.info('Loading market data...')
        return data.get_multi_asset_data(ASSETS, 'M15', DEFAULT_BARS)
    
    def _get_history(self) -> str:
        '''Get recent experiment history.'''
        df = monitor.get_last_experiments(self.db_path, N_LAST_EXPERIMENTS)
        if df.empty:
            return 'No experiments yet.'
        
        lines = []
        for _, row in df.iterrows():
            status = 'OK' if row['is_valid'] else 'FAIL'
            exp_id = row['experiment_id']
            sharpe = row.get('sharpe_wfv') or 0
            reason = row.get('rejection_reason', '') or ''
            lines.append(
                f'- exp {exp_id}: Sharpe={sharpe:.3f} {status} {reason}'
            )
        
        return '\n'.join(lines)
    
    def _save_best(self, strategy_code: str) -> None:
        '''Save as best strategy.'''
        shutil.copy(self.strategy_path, self.best_path)
        logger.info(f'New best strategy saved (Sharpe={self.best_sharpe or 0:.3f})')
    
    def _revert(self) -> None:
        '''Revert to last working strategy.'''
        if self.last_strategy:
            _write_file(self.strategy_path, self.last_strategy)
            logger.info('Strategy reverted to previous version')
    
    def _should_stop(self) -> bool:
        '''Check if agent should stop based on max_experiments or duration.'''
        if self.max_experiments and self.experiment_count >= self.max_experiments:
            logger.info(f'Reached max experiments ({self.max_experiments}), stopping.')
            return True
        
        if self.duration_hours:
            elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds() / 3600
            if elapsed >= self.duration_hours:
                logger.info(f'Reached duration limit ({self.duration_hours}h), stopping.')
                return True
        
        return False
    
    def _run(self) -> None:
        '''Execute single iteration of the loop.'''
        experiment_id = f'exp_{self.experiment_count:04d}'
        logger.info(f'=== Starting {experiment_id} ===')
        
        # 1. Read strategy
        strategy_code = _read_file(self.strategy_path)
        self.last_strategy = strategy_code
        
        # 2. Get history
        history = self._get_history()
        
        # 3. Build prompt
        program_md = _read_file(self.program_path)
        prompt = _build_prompt(program_md, strategy_code, history)
        
        # 4. Call LLM
        logger.info('Calling LLM...')
        response = _call_llm(prompt)
        new_strategy = _parse_llm_response(response)
        
        if not new_strategy or len(new_strategy) < 100:
            logger.warning('LLM returned invalid response, skipping')
            return
        
        # 5. Write new strategy
        _write_file(self.strategy_path, new_strategy)
        
        # 6. Run backtest
        logger.info('Running backtest...')
        metrics = run_experiment(experiment_id, new_strategy, self.data_cache)
        metrics['experiment_id'] = experiment_id
        metrics['timestamp'] = datetime.now(timezone.utc).isoformat()
        
        is_valid = metrics.get('is_valid', False)
        sharpe_wfv = metrics.get('sharpe_wfv', 0.0)
        
        # 7. Compare and decide
        if is_valid and sharpe_wfv > self.best_sharpe:
            self.best_sharpe = sharpe_wfv
            self._save_best(new_strategy)
            status = 'keep'
        else:
            self._revert()
            status = 'discard'
        
        # 8. Log to database
        monitor.log_experiment(
            db_path=self.db_path,
            experiment_id=experiment_id,
            metrics=metrics,
            strategy_hash=_compute_hash(new_strategy),
            description=f'sharpe_wfv={(sharpe_wfv or 0):.3f}',
            status=status,
        )
        
        # 9. Update monitor
        mon = monitor.get_monitor()
        mon.record_experiment(sharpe_wfv, is_valid)
        mon.report_every_n_experiments(n=10)
        
        self.experiment_count += 1
    
    def start(self) -> None:
        '''Start the main loop.'''
        logger.info('=== Autoresearch Agent Starting ===')
        
        # Init database
        monitor.init_db(self.db_path)
        
        # Load data once (cached)
        logger.info('Loading data for first iteration...')
        self.data_cache = self._load_data()
        
        while True:
            try:
                if self._should_stop():
                    break
                
                self._run()
                
                # Cooldown
                logger.info(f'Sleeping {EXPERIMENT_COOLDOWN}s for GPU cooldown...')
                time.sleep(EXPERIMENT_COOLDOWN)
            
            except KeyboardInterrupt:
                logger.info('Keyboard interrupt received, stopping...')
                break
            except Exception as e:
                logger.error(f'Unexpected error in main loop: {e}')
                logger.info('Waiting 30s before retry...')
                time.sleep(30)


def main():
    parser = argparse.ArgumentParser(description='Autoresearch Trading Agent')
    parser.add_argument('--strategy', default='strategy.py', help='Path to strategy file')
    parser.add_argument('--program', default='program.md', help='Path to program.md')
    parser.add_argument('--db', default='experiments.db', help='Path to experiments database')
    parser.add_argument('--best', default='best_strategy.py', help='Path to save best strategy')
    parser.add_argument('--max-experiments', type=int, default=None, help='Max experiments to run')
    parser.add_argument('--duration-hours', type=float, default=None, help='Max hours to run')
    
    args = parser.parse_args()
    
    agent = Agent(
        strategy_path=args.strategy,
        program_path=args.program,
        db_path=args.db,
        best_path=args.best,
        max_experiments=args.max_experiments,
        duration_hours=args.duration_hours,
    )
    agent.start()


if __name__ == '__main__':
    main()