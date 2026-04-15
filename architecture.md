# Arquitectura del Sistema Autoresearch Trading

## Vista General

```
                                          ┌──────────────────┐
                                          │   Humano         │
                                          │   (supervisor)   │
                                          └────────┬─────────┘
                                                   │ instruye
                                                   ▼
                                          ┌──────────────────┐
                                          │   program.md     │  ← Solo editable por humano
                                          └────────┬─────────┘
                                                   │ proporciona contexto
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              AGENTE LLM                                       │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                         agent.py                                      │   │
│   │                      (loop principal)                                 │   │
│   └──────────────────────────────────┬───────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                         strategy.py                                   │   │ ← SÓLO editable por agente
│   │                      (estrategia de trading)                          │   │
│   └──────────────────────────────────┬───────────────────────────────────┘   │
│                                      │                                      │
└──────────────────────────────────────┼──────────────────────────────────────┘
                                       │ modifica
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              MÓDULOS FIJOS                                    │
│                                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  backtest   │  │    data     │  │   execute   │  │    risk     │         │
│  │    .py      │  │    .py      │  │    .py      │  │    .py      │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │                │                │                │                 │
│         │                │                │                │                 │
│         ▼                ▼                ▼                ▼                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  vectorbt   │  │   MT5 +     │  │   MT5 +     │  │  métricas   │         │
│  │  (backtest) │  │   CCXT      │  │   CCXT      │  │  validación │         │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                          │
│  │  monitor    │  │   agent.py  │  │  config.py  │                          │
│  │    .py      │  │  (no-editar)│  │  (secreto)  │                          │
│  └─────────────┘  └─────────────┘  └─────────────┘                          │
└──────────────────────────────────────────────────────────────────────────────┘
                                       │
                              ┌────────┴────────┐
                              ▼                 ▼
                    ┌──────────────┐   ┌──────────────┐
                    │  MetaTrader 5 │   │    CCXT      │
                    │  (Forex/Gold) │   │ (Binance)    │
                    └──────────────┘   └──────────────┘
```

---

## Estructura de Archivos

```
autoresearch-trading/
│
├── program.md              ← Instrucciones del humano (editable por humano)
├── strategy.py             ← Estrategia de trading (editable por AGENTE)
│
├── backtest.py             ← Motor de backtesting con WFV (FIJO)
├── data.py                 ← Descarga/caching de datos OHLCV (FIJO)
├── execute.py              ← Envío de órdenes a MT5/CCXT (FIJO)
├── agent.py                ← Loop principal del autoresearch (FIJO)
├── monitor.py              ← Métricas en tiempo real + Telegram (FIJO)
├── risk.py                 ← Validaciones de riesgo pre-ejecución (FIJO)
│
├── config.py               ← Carga de credenciales desde .env (FIJO)
├── utils.py                ← Helpers comunes (FIJO)
│
├── experiments.db          ← SQLite: log de experimentos (auto-generado)
├── best_strategy.py        ← Snapshot del mejor Shar pe (auto-generado)
├── results.tsv             ← Resultados tabulares (auto-generado)
│
├── logs/                   ← Loguru logs rotados diariamente (auto-generado)
│   └── autoresearch_YYYYMMDD.log
│
├── .env                    ← Credenciales (NO commitear)
├── pyproject.toml          ← Dependencias Python
└── README.md               ← Documentación
```

---

## Flujo de Datos

```
1. DATA FLOW (preparación)
────────────────────────────────────────────────────────────

MT5/CCXT          data.py            data/
   │                 │                  │
   ▼                 ▼                  ▼
OHLCV ──────► download + cache ──────► parquet files
                (auto)                  (~1GB)

2. EXPERIMENT FLOW (backtesting)
────────────────────────────────────────────────────────────

strategy.py ◄──── agent.py (LLM)
    │                  │
    │ propone          │ decide
    ▼                  ▼
generate_signals()  backtest.py
    │                  │
    │                  ▼
    │           ┌─────────────┐
    │           │ vectorbt    │
    │           │ portfolio   │
    │           └──────┬──────┘
    │                  │
    ▼                  ▼
signals          metrics JSON
              (sharpe_wfv, etc.)

3. EXECUTION FLOW (live trading)
────────────────────────────────────────────────────────────

agent.py           risk.py           execute.py
    │                  │                  │
    │ mejor estrategia │ valida │         │ ejecuta
    ▼                  ▼         ▼         ▼
best_strategy.py ◄── OK? ───► MT5/CCXT ──► órdenes
```

---

## Componentes Principales

### 1. `data.py` — Data Layer

**Responsabilidad:** Descargar, normalizar y cachear datos OHLCV.

**Assets soportados:**
- Forex + Metales: `EURUSD`, `GBPUSD`, `USDJPY`, `AUDUSD`, `USDCHF`, `XAUUSD` (via MT5)
- Crypto: `BTC/USDT`, `ETH/USDT`, `SOL/USDT` (via CCXT → Binance/Bybit)

**Interfaces:**
```python
def get_ohlcv(asset: str, timeframe: str, bars: int) -> pd.DataFrame
def get_multi_asset_data(assets: list[str], timeframe: str, bars: int) -> dict[str, pd.DataFrame]
def get_latest_bar(asset: str) -> pd.Series
def is_market_open(asset: str) -> bool
```

**Cache:** Datos guardados en `~/.cache/autoresearch-trading/` como parquet.

---

### 2. `strategy.py` — Strategy Layer

**Responsabilidad:** Definir la lógica de generación de señales de trading.

**Estructura:**
```python
PARAMS = {...}  # hiperparámetros editables

def generate_signals(df: pd.DataFrame) -> pd.Series:
    # return 1 (long), -1 (short), 0 (flat)

def get_position_size(capital: float, price: float, atr: float) -> float:
    # calcula tamaño de posición basado en riesgo
```

**Modificado por:** Agente LLM exclusivamente.

---

### 3. `backtest.py` — Evaluation Layer

**Responsabilidad:** Evaluar estrategias usando Walk-Forward Validation.

**Métricas principales:**
- `sharpe_wfv` = mean(sharpe_oos) - 0.5 * std(sharpe_oos) ← **MÉTRICA PRIMARY**
- `avg_max_drawdown` < 0.15
- `total_trades` >= 200

**Constraints de validación:**
- `sharpe_wfv >= 0` — No perder dinero
- `avg_max_drawdown < 0.15` — Drawdown controlado
- `total_trades >= 200` — Significancia estadística

**Tiempo objetivo:** < 30 segundos por experimento.

---

### 4. `risk.py` — Risk Management Layer

**Responsabilidad:** Validar que cada operación respete los límites de riesgo.

**Checks antes de ejecutar:**
- Size de posición no excede `MAX_POSITION_PCT` del capital
- Stop loss no excede `MAX_LOSS_PCT` por trade
- No ejecutar si `daily_loss >= MAX_DAILY_LOSS_PCT`
- No ejecutar en news de alto impacto (si implementable)

---

### 5. `execute.py` — Execution Layer

**Responsabilidad:** Enviar órdenes a brokers.

**Bridges:**
- MT5 Python API → MetaTrader 5 (Forex/Gold)
- CCXT → Binance/Bybit (Crypto)

**Modes:**
- `paper` — Órdenes simuladas en cuenta demo
- `live` — Órdenes reales con dinero

---

### 6. `monitor.py` — Monitoring Layer

**Responsabilidad:** Rastrear métricas y alertar.

**Métricas rastreadas:**
- P&L actual vs. capital inicial
- Drawdown actual
- Sharpe ratio en ventana móvil
- Número de trades hoy

**Alertas Telegram:**
- Cada 10 experimentos: resumen de resultados
- Si `sharpe_wfv < 0` por 5 experimentos
- Si `drawdown >= 12%`

---

### 7. `agent.py` — Orchestration Layer

**Responsabilidad:** Loop principal del autoresearch.

```
LOOP:
 1. Leer strategy.py + program.md + historial
 2. Construir prompt para LLM
 3. Llamar LLM → obtener nueva estrategia
 4. Escribir strategy.py
 5. Run backtest.py → obtener métricas
 6. Comparar con mejor
 7. Si mejora → guardar best_strategy.py
    Si no → revertir
 8. Log en experiments.db
 9. Reportar por Telegram si toca
 10. Sleep 60s
 11. GOTO 1
```

---

### 8. `config.py` — Configuration Layer

**Responsabilidad:** Cargar y validar credenciales desde `.env`.

**Variables de entorno requeridas:**
```python
# LLM
OPENROUTER_API_KEY
OLLAMA_BASE_URL
LLM_PROVIDER=ollama|openrouter
LLM_MODEL

# Brokers
MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
BINANCE_API_KEY, BINANCE_SECRET, BINANCE_TESTNET

# Sistema
MODE=paper|live
MAX_DAILY_LOSS_PCT=0.02

# WFV
WFV_N_WINDOWS=6
WFV_TRAIN_BARS=3000
WFV_TEST_BARS=1000
WFV_STEP_BARS=1000
```

---

## Walk-Forward Validation (WFV)

```
Temporal axis: ──────────────────────────────────────────────────────────►

Window 1:  │████████████│████████│
           Train (3000)  Test(1000)

Window 2:       │████████████│████████│
                Train (3000)  Test(1000)

Window 3:            │████████████│████████│
                     Train (3000)  Test(1000)

... (6 windows total)

sharpe_wfv = mean([sharpe_oos_w1, sharpe_oos_w2, ..., sharpe_oos_w6])
             - 0.5 * std([sharpe_oos_w1, sharpe_oos_w2, ..., sharpe_oos_w6])
```

**Por qué WFV:**
- Más robusto que split 80/20 estático
- Evalúa estabilidad temporal de la estrategia
- Penaliza varianza (estrategia estable > estrategia errática)

---

## Base de Datos (SQLite)

### Tabla: `experiments`
```sql
CREATE TABLE experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT UNIQUE NOT NULL,
    timestamp TEXT NOT NULL,
    
    -- Métricas principales
    sharpe_wfv REAL,
    sharpe_mean_oos REAL,
    sharpe_std_oos REAL,
    
    -- Métricas secundarias
    avg_max_drawdown REAL,
    total_trades INTEGER,
    avg_win_rate REAL,
    avg_profit_factor REAL,
    
    -- Validación
    is_valid BOOLEAN,
    rejection_reason TEXT,
    
    -- Estrategia
    strategy_hash TEXT,
    description TEXT,
    
    -- Resultado
    status TEXT CHECK(status IN ('keep', 'discard', 'crash')),
    
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Tabla: `window_results`
```sql
CREATE TABLE window_results (
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
);
```

---

## Dependencias

```
┌─────────────────────────────────────────────────────────────┐
│                    pyproject.toml                          │
├─────────────────────────────────────────────────────────────┤
│  MetaTrader5     # data + ejecución forex/gold             │
│  ccxt             # data + ejecución crypto                 │
│  vectorbt         # backtesting vectorizado                 │
│  pandas           # manipulación de datos                   │
│  numpy            # cálculos                                │
│  ta-lib           # indicadores técnicos                    │
│  pandas-ta        # alternativa a ta-lib                    │
│  openai           # cliente LLM (ollama + openrouter)       │
│  python-telegram-bot  # alertas                             │
│  loguru           # logging estructurado                    │
│  sqlalchemy       # ORM para SQLite                         │
│  apscheduler      # scheduling                              │
│  python-dotenv    # variables de entorno                    │
│  psutil           # monitoreo de recursos                   │
│  rich             # output en consola                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Environment Variables (.env)

```bash
# LLM (requerido)
OPENROUTER_API_KEY=sk-or-...
OLLAMA_BASE_URL=http://localhost:11434/v1
LLM_PROVIDER=ollama
LLM_MODEL=deepseek-r1:14b

# MT5 (requerido para forex)
MT5_LOGIN=123456
MT5_PASSWORD=secret
MT5_SERVER=Broker-Demo

# CCXT/Binance (requerido para crypto)
BINANCE_API_KEY=...
BINANCE_SECRET=...
BINANCE_TESTNET=true

# Telegram (opcional)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# Sistema
MODE=paper
MAX_DAILY_LOSS_PCT=0.02

# WFV
WFV_N_WINDOWS=6
WFV_TRAIN_BARS=3000
WFV_TEST_BARS=1000
WFV_STEP_BARS=1000
```

---

## Constraints de Diseño

| Constraint | Valor | Razón |
|------------|-------|-------|
| Time budget por backtest | < 30s | Iteración rápida |
| VRAM disponible | ~16GB | RTX 4060 Ti |
| Walk-forward windows | 6 | Balance robustez/velocidad |
| Train bars por window | 3000 | ~31 días M15 |
| Test bars por window | 1000 | ~10 días M15 |
| Step bars | 1000 | ~10 días entre ventanas |