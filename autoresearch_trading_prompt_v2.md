# AUTORESEARCH TRADING SYSTEM — CODING AGENT INSTRUCTIONS

## ROL Y OBJETIVO

Eres un ingeniero senior especializado en sistemas de trading algorítmico y agentes LLM autónomos. Tu tarea es construir desde cero un sistema completo de **autoresearch para trading**, inspirado en el repositorio `karpathy/autoresearch`, adaptado para operar en mercados de Forex, metales y criptomonedas de forma autónoma.

El sistema debe:
1. Usar un agente LLM que modifique iterativamente una estrategia de trading
2. Evaluar cada modificación mediante backtest rápido (~30s)
3. Conservar los cambios que mejoren el Sharpe ratio, descartar los que no
4. Operar en modo paper trading para validación
5. Escalar a dinero real solo cuando las métricas lo justifiquen

---

## HARDWARE Y ENTORNO

- **OS**: Windows (el usuario puede tener WSL2 o PowerShell)
- **GPU**: RTX 4060 Ti 16GB VRAM
- **RAM**: 32GB
- **CPU**: Intel i5-12400F
- **LLM local**: `ollama` con `deepseek-r1:14b` (cabe completo en VRAM)
- **LLM remoto (backup)**: OpenRouter API — compatible con OpenAI SDK — modelos: `minimax/minimax-m1` o `thudm/glm-4-plus`
- **Python**: 3.11+ con `uv` como gestor de paquetes

---

## ASSETS A OPERAR

### Forex + Metales (vía MetaTrader 5)
```
EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF, XAUUSD
```

### Crypto (vía CCXT — Binance o Bybit)
```
BTC/USDT, ETH/USDT, SOL/USDT
```

**Timeframe principal**: M15 (15 minutos)
**Timeframes auxiliares para contexto**: H1, H4

---

## STACK TECNOLÓGICO COMPLETO

### Dependencias Python (pyproject.toml con uv)
```toml
[project]
name = "autoresearch-trading"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "MetaTrader5",          # data + ejecución forex/gold
    "ccxt",                 # data + ejecución crypto
    "vectorbt",             # backtesting vectorizado rápido
    "pandas",
    "numpy",
    "ta-lib",               # indicadores técnicos
    "pandas-ta",            # alternativa/complemento a ta-lib
    "openai",               # cliente para OpenRouter Y ollama (ambos OpenAI-compatible)
    "python-telegram-bot",  # alertas
    "loguru",               # logging estructurado
    "sqlalchemy",           # ORM para SQLite
    "apscheduler",          # scheduling del loop
    "python-dotenv",        # variables de entorno
    "psutil",               # monitoreo de recursos del sistema
    "rich",                 # output bonito en consola
]
```

### Variables de entorno (.env)
```
# LLM
OPENROUTER_API_KEY=sk-or-...
OLLAMA_BASE_URL=http://localhost:11434/v1
LLM_PROVIDER=ollama          # "ollama" | "openrouter"
LLM_MODEL=deepseek-r1:14b    # o minimax/minimax-m1 para openrouter

# MT5
MT5_LOGIN=123456
MT5_PASSWORD=...
MT5_SERVER=...

# CCXT / Binance
BINANCE_API_KEY=...
BINANCE_SECRET=...
BINANCE_TESTNET=true         # true para paper, false para live

# Bybit (alternativa)
BYBIT_API_KEY=...
BYBIT_SECRET=...
BYBIT_TESTNET=true

# Telegram
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# Sistema
MODE=paper                   # "paper" | "live"
MAX_DAILY_LOSS_PCT=0.02      # 2% drawdown diario → circuit breaker

# Walk-Forward Validation
WFV_N_WINDOWS=6              # número de ventanas deslizantes
WFV_TRAIN_BARS=3000          # barras de entrenamiento por ventana (M15 ≈ 31 días)
WFV_TEST_BARS=1000           # barras de test por ventana (M15 ≈ 10 días)
WFV_STEP_BARS=1000           # desplazamiento de la ventana entre iteraciones
```

---

## ESTRUCTURA DE ARCHIVOS

```
autoresearch-trading/
│
├── program.md              ← INSTRUCCIONES PARA EL AGENTE (humano edita esto)
├── strategy.py             ← ARCHIVO QUE EL AGENTE MODIFICA EN CADA LOOP
│
├── backtest.py             ← FIJO — corre vectorbt con walk-forward, devuelve métricas JSON
├── data.py                 ← FIJO — descarga OHLCV de todos los assets
├── execute.py              ← FIJO — envía órdenes a MT5 y CCXT
├── agent.py                ← FIJO — loop principal del autoresearch
├── monitor.py              ← FIJO — métricas en tiempo real, alertas Telegram
├── risk.py                 ← FIJO — validaciones de riesgo antes de ejecutar
│
├── experiments.db          ← SQLite: log de cada experimento
├── best_strategy.py        ← snapshot automático del mejor Sharpe
├── logs/                   ← loguru logs rotados diariamente
│
├── .env
├── pyproject.toml
└── program.md
```

**REGLA CRÍTICA**: Los archivos `backtest.py`, `data.py`, `execute.py`, `agent.py`, `monitor.py` y `risk.py` son **intocables por el agente LLM**. Solo `strategy.py` es modificado en el loop. El humano edita `program.md`.

---

## ESPECIFICACIONES DE CADA ARCHIVO

---

### `data.py` — Data Layer

Responsabilidades:
- Descargar OHLCV histórico de MT5 (forex + XAUUSD) y CCXT (crypto)
- Proveer datos en tiempo real para ejecución live
- Normalizar todos los datos a un formato pandas DataFrame uniforme con columnas: `timestamp, open, high, low, close, volume, asset, timeframe`
- Cachear datos localmente para evitar descargas repetidas en el loop

Funciones requeridas:
```python
def get_ohlcv(asset: str, timeframe: str, bars: int) -> pd.DataFrame
def get_multi_asset_data(assets: list[str], timeframe: str, bars: int) -> dict[str, pd.DataFrame]
def get_latest_bar(asset: str) -> pd.Series
def is_market_open(asset: str) -> bool
```

Notas:
- MT5 debe inicializarse una sola vez con context manager
- CCXT debe soportar tanto Binance como Bybit, configurable por .env
- En modo testnet, usar los endpoints correspondientes de Binance Futures Testnet
- Para MT5 en paper: usar cuenta demo, mismas funciones que live
- Manejar reconexiones automáticas si MT5 se desconecta

---

### `strategy.py` — El archivo que modifica el agente

Este archivo contiene la lógica completa de la estrategia de trading. El agente lo lee, propone una modificación, lo reescribe, y `backtest.py` lo evalúa automáticamente.

Estructura base inicial (el agente la mejorará):
```python
"""
Strategy v1 — baseline
Descripción: [el agente actualiza esto en cada versión]
Cambios respecto a versión anterior: [el agente documenta aquí]
"""

import pandas as pd
import pandas_ta as ta

# ─── PARÁMETROS (el agente puede modificar estos) ───────────────────────────
PARAMS = {
    "ema_fast": 9,
    "ema_slow": 21,
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "atr_period": 14,
    "sl_atr_mult": 1.5,
    "tp_atr_mult": 2.5,
    "position_size_pct": 0.02,  # 2% del capital por trade
}

def generate_signals(df: pd.DataFrame) -> pd.Series:
    """
    Input: OHLCV DataFrame con columnas open, high, low, close, volume
    Output: pd.Series con valores 1 (long), -1 (short), 0 (flat)
    """
    # baseline: EMA crossover + RSI filter
    df["ema_fast"] = ta.ema(df["close"], length=PARAMS["ema_fast"])
    df["ema_slow"] = ta.ema(df["close"], length=PARAMS["ema_slow"])
    df["rsi"] = ta.rsi(df["close"], length=PARAMS["rsi_period"])
    
    signal = pd.Series(0, index=df.index)
    signal[(df["ema_fast"] > df["ema_slow"]) & (df["rsi"] < PARAMS["rsi_overbought"])] = 1
    signal[(df["ema_fast"] < df["ema_slow"]) & (df["rsi"] > PARAMS["rsi_oversold"])] = -1
    
    return signal

def get_position_size(capital: float, price: float, atr: float) -> float:
    """Calcula el tamaño de posición basado en volatilidad (ATR)"""
    risk_amount = capital * PARAMS["position_size_pct"]
    sl_distance = atr * PARAMS["sl_atr_mult"]
    return risk_amount / sl_distance
```

---

### `backtest.py` — Motor de evaluación con Walk-Forward Validation

El backtest debe ser **rápido** (objetivo < 30 segundos para 2 años de datos M15 en 9 assets).

#### ⚠️ Método de validación: Ventana Deslizante (Walk-Forward)

**NO se usa un split estático 80/20.** En su lugar se implementa **Walk-Forward Validation (WFV)** con ventanas deslizantes, lo cual es más robusto frente a overfitting temporal y más representativo del comportamiento real de la estrategia en producción.

El esquema de ventanas es el siguiente:

```
Datos totales: ──────────────────────────────────────────────────────►
               │     TRAIN_1     │ TEST_1 │
                        │     TRAIN_2     │ TEST_2 │
                                  │     TRAIN_3     │ TEST_3 │
                                           │     TRAIN_4     │ TEST_4 │
                                                    │     TRAIN_5     │ TEST_5 │
                                                             │     TRAIN_6     │ TEST_6 │
```

- **`WFV_TRAIN_BARS`**: barras de entrenamiento por ventana (por defecto 3000 ≈ 31 días en M15)
- **`WFV_TEST_BARS`**: barras de test por ventana (por defecto 1000 ≈ 10 días en M15)
- **`WFV_STEP_BARS`**: cuántas barras avanza la ventana en cada iteración (por defecto 1000)
- **`WFV_N_WINDOWS`**: número de ventanas (por defecto 6)

La **métrica principal** (`sharpe_wfv`) es el **promedio del Sharpe ratio OOS de todas las ventanas**, penalizado por su desviación estándar entre ventanas:

```
sharpe_wfv = mean(sharpe_oos_per_window) - 0.5 * std(sharpe_oos_per_window)
```

La penalización por std captura la **estabilidad temporal** de la estrategia: una estrategia que funciona bien en todas las épocas vale más que una que funciona muy bien en una sola.

Implementación requerida en `backtest.py`:

```python
import importlib
import importlib.util
import pandas as pd
import numpy as np
import vectorbt as vbt
from pathlib import Path
from typing import NamedTuple
import os

WFV_TRAIN_BARS = int(os.getenv("WFV_TRAIN_BARS", 3000))
WFV_TEST_BARS  = int(os.getenv("WFV_TEST_BARS",  1000))
WFV_STEP_BARS  = int(os.getenv("WFV_STEP_BARS",  1000))
WFV_N_WINDOWS  = int(os.getenv("WFV_N_WINDOWS",  6))

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

def generate_walk_forward_windows(total_bars: int) -> list[tuple[int,int,int,int]]:
    """
    Genera los índices (train_start, train_end, test_start, test_end) 
    para cada ventana deslizante.
    Retorna lista de tuplas ordenadas cronológicamente.
    Las ventanas NO se solapan en el segmento de test (anchored o rolling).
    """
    windows = []
    for i in range(WFV_N_WINDOWS):
        train_start = i * WFV_STEP_BARS
        train_end   = train_start + WFV_TRAIN_BARS
        test_start  = train_end
        test_end    = test_start + WFV_TEST_BARS
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
    Corre la estrategia en el segmento TEST de una ventana.
    Los parámetros de la estrategia son fijos (definidos en strategy.py).
    Si en el futuro se implementa optimización de parámetros, esta función
    recibiría los params optimizados sobre TRAIN y los aplicaría en TEST.
    Retorna métricas del segmento OOS.
    """
    df_test = df_asset.iloc[test_start:test_end].copy()
    signals = strategy_module.generate_signals(df_test)
    
    entries = signals == 1
    exits   = signals == -1
    
    portfolio = vbt.Portfolio.from_signals(
        close=df_test["close"],
        entries=entries,
        exits=exits,
        init_cash=10_000,
        fees=0.0002,
        slippage=0.0001,
    )
    
    stats = portfolio.stats()
    total_return = portfolio.total_return()
    
    sharpe    = float(stats.get("Sharpe Ratio", 0.0) or 0.0)
    max_dd    = float(abs(stats.get("Max Drawdown [%]", 0.0) or 0.0)) / 100.0
    n_trades  = int(stats.get("Total Trades", 0) or 0)
    win_rate  = float(stats.get("Win Rate [%]", 0.0) or 0.0) / 100.0
    
    gross_profit = float(stats.get("Gross Profit [$]", 0.0) or 0.0)
    gross_loss   = abs(float(stats.get("Gross Loss [$]", 1.0) or 1.0))
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
    Ejecuta Walk-Forward Validation sobre todos los assets.
    La métrica principal (sharpe_wfv) es el promedio de sharpes OOS 
    entre ventanas y assets, penalizado por su desviación estándar.
    """
    all_window_sharpes: list[float] = []
    all_window_results: list[WindowResult] = []
    per_asset_wfv: dict[str, float] = {}
    
    for asset, df in data.items():
        total_bars = len(df)
        windows = generate_walk_forward_windows(total_bars)
        
        if not windows:
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
        
        # Sharpe WFV por asset: media - 0.5 * std (penalización estabilidad)
        per_asset_wfv[asset] = (
            float(np.mean(asset_sharpes)) - 0.5 * float(np.std(asset_sharpes))
        )
    
    if not all_window_sharpes:
        return {"is_valid": False, "rejection_reason": "No se generaron ventanas válidas"}
    
    sharpe_mean = float(np.mean(all_window_sharpes))
    sharpe_std  = float(np.std(all_window_sharpes))
    sharpe_wfv  = sharpe_mean - 0.5 * sharpe_std  # métrica principal
    
    avg_dd      = float(np.mean([r.max_drawdown for r in all_window_results]))
    total_trades = int(np.sum([r.total_trades for r in all_window_results]))
    avg_wr      = float(np.mean([r.win_rate for r in all_window_results]))
    avg_pf      = float(np.mean([r.profit_factor for r in all_window_results]))
    
    # Constraints de validación
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
        "sharpe_wfv": sharpe_wfv,          # ← MÉTRICA PRINCIPAL (reemplaza sharpe_oos)
        "sharpe_mean_oos": sharpe_mean,    # media cruda de sharpes OOS
        "sharpe_std_oos": sharpe_std,      # std entre ventanas (estabilidad)
        "n_windows": len(all_window_sharpes),
        "avg_max_drawdown": avg_dd,
        "total_trades": total_trades,
        "avg_win_rate": avg_wr,
        "avg_profit_factor": avg_pf,
        "per_asset_wfv": per_asset_wfv,
        "window_sharpes": all_window_sharpes,  # lista de sharpes por ventana para debug
        "is_valid": is_valid,
        "rejection_reason": rejection_reason,
    }
```

Métricas completas a calcular y retornar (dict JSON-serializable):
```python
{
    "experiment_id": "exp_0042",
    "timestamp": "2025-04-15T02:31:00",
    
    # ── Walk-Forward Metrics (métricas principales) ──────────────────────
    "sharpe_wfv": 1.31,             # ← MÉTRICA PRINCIPAL: mean(OOS) - 0.5*std(OOS)
    "sharpe_mean_oos": 1.47,        # promedio de sharpes en ventanas OOS
    "sharpe_std_oos": 0.32,         # desv. estándar entre ventanas (robustez)
    "n_windows": 6,                 # número de ventanas evaluadas
    "window_sharpes": [1.2, 1.5, 1.3, 1.8, 1.4, 1.6],  # sharpe por ventana
    
    # ── Métricas agregadas ───────────────────────────────────────────────
    "avg_max_drawdown": 0.087,      # < 0.15 requerido
    "total_trades": 847,            # > 200 requerido (suma de todas las ventanas)
    "avg_win_rate": 0.54,
    "avg_profit_factor": 1.61,
    
    # ── Breakdown por asset ──────────────────────────────────────────────
    "per_asset_wfv": {
        "EURUSD": 1.1,
        "XAUUSD": 1.8,
        "BTCUSDT": 1.2,
        ...
    },
    
    # ── Validación ───────────────────────────────────────────────────────
    "is_valid": true,
    "rejection_reason": null,
    "strategy_hash": "a3f9b2...",
}
```

Constraints de validación (si no se cumplen → `is_valid=false`, el agente descarta):
- `sharpe_wfv >= 0` (no perder dinero en promedio OOS)
- `avg_max_drawdown < 0.15` (nunca más del 15% drawdown promedio)
- `total_trades >= 200` (suficiente significancia estadística en total de ventanas)
- El strategy no debe dar error de ejecución

---

### `agent.py` — El loop autoresearch

Este es el corazón del sistema. Implementa el loop:

```
LOOP:
  1. Leer strategy.py actual
  2. Leer últimos N experimentos de experiments.db
  3. Construir prompt con: program.md + strategy.py + historial
  4. Llamar al LLM → obtener nuevo strategy.py
  5. Escribir nuevo strategy.py
  6. Correr backtest.py (walk-forward)
  7. Comparar sharpe_wfv con el mejor hasta ahora
  8. Si mejora → guardar como best_strategy.py + log éxito
     Si no mejora → revertir strategy.py a versión anterior + log descarte
  9. Enviar resumen por Telegram cada 10 experimentos
  10. Esperar configuración (ej. 60s entre experimentos para no calentar GPU)
  11. Repetir
```

Requerimientos técnicos:
- Soportar ambos backends LLM (ollama + OpenRouter) con la misma interfaz usando el cliente `openai`
- Para ollama: `base_url="http://localhost:11434/v1"`, `api_key="ollama"`
- Para OpenRouter: `base_url="https://openrouter.ai/api/v1"`, `api_key=OPENROUTER_API_KEY`
- El LLM DEBE retornar SOLO el contenido del archivo Python, sin markdown fences, sin explicaciones extra. Parsear con regex si es necesario extraer el código
- Implementar timeout por llamada al LLM (120 segundos) con fallback
- Si el LLM genera código con SyntaxError → contar como experimento fallido, revertir, continuar
- Guardar TODOS los experimentos en SQLite independientemente del resultado
- Implementar `--max-experiments N` y `--duration-hours H` como argumentos CLI
- Al terminar el loop, imprimir resumen con tabla de top-10 experimentos

---

### `risk.py` — Risk Management

Validaciones ANTES de enviar cualquier orden a execute.py:

```python
class RiskManager:
    def validate_order(self, asset, direction, size, price, sl, tp) -> tuple[bool, str]:
        """Retorna (is_approved, reason)"""
    
    def check_daily_loss(self) -> bool:
        """True si el PnL del día supera el MAX_DAILY_LOSS_PCT → circuit breaker"""
    
    def check_correlation(self, asset, direction) -> bool:
        """Evitar posiciones altamente correlacionadas simultáneas
           (ej: long EURUSD y long GBPUSD al mismo tiempo)"""
    
    def get_max_size(self, asset, capital) -> float:
        """Kelly fraction con cap en 2% de capital por trade"""
    
    def emergency_close_all(self):
        """Cierra todas las posiciones abiertas en MT5 y CCXT"""
```

Circuit breakers:
- Si PnL diario < -2% del capital → `emergency_close_all()` + alerta Telegram + detener loop
- Si 3 errores consecutivos de conexión → detener y alertar
- Si drawdown de la cuenta supera 10% → modo solo-paper hasta reset manual

---

### `execute.py` — Ejecución de Órdenes

Wrapper unificado que abstrae MT5 y CCXT:

```python
def place_order(asset: str, direction: str, size: float, 
                sl: float, tp: float, comment: str) -> dict:
    """
    Detecta automáticamente si el asset es forex/gold (→ MT5) o crypto (→ CCXT)
    Retorna: {"order_id": ..., "status": "filled"|"error", "fill_price": ...}
    """

def close_position(asset: str, position_id: str) -> dict:
    ...

def get_open_positions() -> list[dict]:
    ...

def get_account_balance() -> dict:
    """Retorna balance consolidado de MT5 + CCXT en USD"""
```

En modo paper (`MODE=paper` en .env):
- MT5: usar cuenta demo, mismas funciones
- CCXT: usar testnet endpoints
- La lógica de `execute.py` no cambia — solo la configuración en .env

---

### `monitor.py` — Monitoreo y Alertas

Responsabilidades:
- Enviar resumen de experimentos a Telegram cada 10 loops
- Alerta inmediata si: circuit breaker activado, error crítico, nuevo best Sharpe encontrado
- Comando `/status` en el bot de Telegram para pedir estado en cualquier momento
- Comando `/stop` para detener el loop de forma segura
- Loggear todo con `loguru` con rotación diaria y retención de 30 días

Formato del mensaje Telegram de resumen:
```
🤖 Autoresearch Update — Exp #42
──────────────────────────
✅ Best Sharpe WFV: 1.74 (exp #38)
📊 Este batch: 3 mejoras / 7 descartes
💹 Mejor asset WFV: XAUUSD (1.80)
📉 Avg DD best: 8.3% | Std Sharpe: 0.28
🔄 Trades best: 1,203 | Ventanas: 6
──────────────────────────
▶️ Loop activo | Mode: PAPER
```

---

### `program.md` — Instrucciones del Agente

Crear este archivo con el siguiente contenido base (el humano lo refina con el tiempo):

```markdown
# Trading Research Agent — Program

## Objetivo
Maximizar el Sharpe ratio walk-forward (sharpe_wfv) en validación out-of-sample
con ventana deslizante sobre datos históricos, operando en todos los assets
con estrategia unificada adaptada por asset.

## Assets
Forex: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF, XAUUSD
Crypto: BTC/USDT, ETH/USDT, SOL/USDT
Timeframe: M15

## Métrica de evaluación
La métrica principal es `sharpe_wfv = mean(OOS_sharpes) - 0.5 * std(OOS_sharpes)`.
Una estrategia es mejor si funciona de forma ESTABLE en TODAS las ventanas temporales,
no solo en una época favorable. Prioriza la robustez temporal sobre el rendimiento pico.

## Tu tarea en cada experimento
1. Leer el `strategy.py` actual y los últimos resultados (incluyendo window_sharpes)
2. Identificar qué mejorar: parámetros, lógica de señales, filtros, position sizing
3. Analizar si la estrategia falla en ventanas específicas (high std → instabilidad)
4. Proponer UNA modificación concreta y bien razonada
5. Reescribir `strategy.py` completo con la modificación
6. Documentar el cambio en el docstring del archivo

## Reglas
- Retorna ÚNICAMENTE el contenido del archivo Python, sin markdown, sin explicaciones externas
- Haz UNA modificación por experimento, no múltiples a la vez
- Documenta en el docstring: qué cambiaste y por qué esperas mejorar sharpe_wfv
- El código debe ser ejecutable sin errores
- No importes librerías no disponibles en el proyecto
- Librerías disponibles: pandas, numpy, pandas_ta, ta (ta-lib), vectorbt

## Estrategias a explorar
- Indicadores técnicos: EMA, SMA, RSI, MACD, Bollinger Bands, ATR, Stochastic, CCI, ADX
- Filtros de tendencia (operar solo en tendencia)
- Filtros de volatilidad (evitar rangos o buscarlos)
- Multi-timeframe: usar H1/H4 como filtro de dirección
- Position sizing dinámico basado en ATR
- Diferentes SL/TP ratios por asset (ej. XAUUSD y BTC necesitan SL más amplio)
- Combinar señales de múltiples indicadores
- Filtros de sesión (horario de Londres/NY para forex)
- Estrategias que reduzcan la varianza entre ventanas (más estables temporalmente)

## Constraints que NUNCA puedes violar
- avg_max_drawdown < 15%
- total_trades >= 200
- position_size_pct <= 0.03 (máximo 3% por trade)
- No usar lookahead bias (nunca usar datos futuros en la señal)
- SL obligatorio en todas las órdenes
```

---

## FLUJO COMPLETO DEL SISTEMA

### Fase 1: Setup inicial
```bash
# 1. Instalar uv
pip install uv

# 2. Crear proyecto
uv init autoresearch-trading
cd autoresearch-trading
uv sync

# 3. Instalar ollama y modelo
# Descargar ollama desde https://ollama.ai
ollama pull deepseek-r1:14b

# 4. Configurar .env con credenciales MT5 y CCXT testnet

# 5. Preparar datos históricos (descarga única)
uv run python data.py --prepare

# 6. Verificar que el backtest walk-forward base funciona
uv run python backtest.py --test
```

### Fase 2: Loop autoresearch (overnight)
```bash
# Correr 100 experimentos (aprox 8 horas con deepseek-r1:14b local)
uv run python agent.py --max-experiments 100 --provider ollama

# O con tiempo fijo
uv run python agent.py --duration-hours 8 --provider ollama

# Por la mañana revisar resultados
uv run python agent.py --show-results --top 10
```

### Fase 3: Paper trading
```bash
# Activar paper trading con la best_strategy.py
uv run python execute.py --mode paper --strategy best_strategy.py

# Monitorear en tiempo real
uv run python monitor.py --live
```

### Fase 4: Live (solo cuando paper trading sea estable >4 semanas)
```bash
# Cambiar MODE=live en .env (única diferencia)
uv run python execute.py --mode live --strategy best_strategy.py
```

---

## CRITERIOS PARA PASAR A DINERO REAL

Implementar una función `is_ready_for_live()` en `monitor.py` que evalúe:

```python
LIVE_READINESS_CRITERIA = {
    "min_paper_weeks": 4,
    "min_sharpe_wfv_paper": 1.5,       # sharpe_wfv en paper trading, no sharpe simple
    "max_drawdown_paper": 0.08,        # más estricto que backtest
    "min_trades_paper": 100,
    "profit_factor_min": 1.4,
    "consecutive_profitable_weeks": 3,
    "max_sharpe_std_paper": 0.5,       # la estabilidad importa: no aceptar alta varianza
}
```

Si no se cumplen todos los criterios → el sistema debe NEGARSE a cambiar a live y mostrar qué criterio falta.

---

## CONSIDERACIONES DE CALIDAD DE CÓDIGO

- Usar type hints en todas las funciones
- Docstrings en todas las funciones públicas
- Manejo de excepciones explícito — nunca `except: pass`
- Logging con loguru en lugar de print (excepto output de consola con rich)
- Tests unitarios básicos para `backtest.py` y `risk.py`
- El sistema debe poder reiniciarse en cualquier punto sin perder estado (SQLite persiste todo)
- Graceful shutdown: al recibir SIGINT, terminar el experimento actual, guardar estado, salir limpio

---

## ADVERTENCIAS Y EDGE CASES A MANEJAR

- MT5 puede desconectarse durante la noche → reconexión automática con retry exponential backoff
- CCXT puede tener rate limits → respetar con `time.sleep` entre llamadas
- El LLM puede generar código con imports incorrectos → validar antes de ejecutar con `ast.parse()`
- El LLM puede intentar modificar archivos fuera de strategy.py → validar que solo retorna código Python puro
- Datos faltantes/NaN en OHLCV → forward fill o drop, nunca propagar NaN a la estrategia
- XAUUSD en MT5 puede tener símbolo diferente según broker (XAUUSDm, GOLD) → hacerlo configurable
- Binance Testnet tiene datos limitados → tener fallback a datos históricos cacheados para backtest
- Si deepseek-r1:14b está ocupado (GPU saturada) → implementar queue con timeout
- **Walk-Forward**: si los datos totales son insuficientes para `WFV_N_WINDOWS` ventanas completas, reducir automáticamente el número de ventanas y loggear advertencia. Mínimo 3 ventanas para que la métrica sea estadísticamente útil.

---

## ENTREGABLES FINALES

El agente de código debe producir todos los archivos listados en la estructura del proyecto, completamente funcionales, con:
1. `data.py` — data layer completo para MT5 + CCXT
2. `strategy.py` — estrategia baseline funcional
3. `backtest.py` — motor de evaluación con Walk-Forward Validation (VectorBT)
4. `agent.py` — loop autoresearch completo
5. `risk.py` — risk management con circuit breakers
6. `execute.py` — ejecución unificada MT5 + CCXT
7. `monitor.py` — alertas Telegram + logging
8. `program.md` — instrucciones del agente trading
9. `pyproject.toml` — dependencias completas
10. `.env.example` — template de variables de entorno
11. `README.md` — instrucciones de setup paso a paso

Todo el código debe ser **ejecutable desde el primer intento** en el entorno descrito.
