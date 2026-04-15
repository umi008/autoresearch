# Autoresearch Trading

Sistema de investigación autónoma para trading algorítmico, inspirado en [`karpathy/autoresearch`](https://github.com/karpathy/autoresearch).

El sistema usa un **agente LLM** que modifica iterativamente una estrategia de trading, la evalúa mediante backtesting con Walk-Forward Validation, y conserva únicamente los cambios que mejoran el Sharpe ratio.

---

## Assets Operados

### Forex + Metales (via MetaTrader 5)
```
EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF, XAUUSD
```

**Timeframe principal:** M15 (15 minutos)

---

## Quick Start

```bash
# 1. Instalar dependencias
uv sync

# 2. Configurar credenciales
cp .env.example .env
# Editar .env con tus API keys

# 3. Preparar datos históricos
uv run python prepare.py

# 4. Ejecutar loop de experimentación
uv run python agent.py
```

---

## Estructura del Proyecto

```
autoresearch/
├── program.md              ← Instrucciones para el agente (humano edita)
├── strategy.py             ← Estrategia de trading (agente modifica)
│
├── backtest.py             ← Motor de backtesting con WFV [FIJO]
├── data.py                 ← Descarga/caching de datos OHLCV [FIJO]
├── execute.py              ← Envío de órdenes a MT5 [FIJO]
├── agent.py                ← Loop principal del autoresearch [FIJO]
├── monitor.py              ← Métricas + alertas [FIJO]
├── risk.py                 ← Validaciones de riesgo [FIJO]
├── config.py               ← Carga de credenciales [FIJO]
│
├── experiments.db          ← SQLite: log de experimentos
├── best_strategy.py        ← Snapshot del mejor Sharpe
├── results.tsv             ← Resultados tabulares
│
├── agents.md               ← Roles y responsabilidades del agente
├── architecture.md          ← Arquitectura del sistema
├── .env                    ← Credenciales (NO commitear)
└── pyproject.toml          ← Dependencias
```

### Archivos Editables vs Fijos

| Archivo | Editable por | Propósito |
|---------|-------------|-----------|
| `program.md` | Humano | Instrucciones para el agente |
| `strategy.py` | Agente LLM | Lógica de trading |
| `backtest.py` | NINGUNO | Métrica fija de comparación |
| `data.py` | NINGUNO | Interface de datos estable |
| `execute.py` | NINGUNO | Ejecución predecible |
| `agent.py` | NINGUNO | Loop principal no mutable |
| `monitor.py` | NINGUNO | Alertas consistentes |
| `risk.py` | NINGUNO | Validaciones innegociables |

---

## Métricas de Validación

### Walk-Forward Validation (WFV)

El sistema usa **ventanas deslizantes** en lugar de un split 80/20 estático:

```
Datos:  TRAIN_1 | TEST_1 | TRAIN_2 | TEST_2 | ... | TRAIN_6 | TEST_6

sharpe_wfv = mean(sharpe_oos_windows) - 0.5 * std(sharpe_oos_windows)
```

### Constraints

| Métrica | Requerimiento | Razón |
|---------|--------------|-------|
| `sharpe_wfv` | ≥ 0 | No perder dinero en promedio |
| `avg_max_drawdown` | < 0.15 | Nunca > 15% drawdown |
| `total_trades` | ≥ 200 | Significancia estadística |

### Métricas Reportadas

```python
{
    "sharpe_wfv": 1.31,          # ← MÉTRICA PRINCIPAL
    "sharpe_mean_oos": 1.47,
    "sharpe_std_oos": 0.32,
    "avg_max_drawdown": 0.087,
    "total_trades": 847,
    "avg_win_rate": 0.54,
    "avg_profit_factor": 1.61,
    "is_valid": true
}
```

---

## Configuración

### Variables de Entorno (.env)

```bash
# LLM (requerido)
OPENROUTER_API_KEY=sk-or-...
LLM_MODEL=minimax/minimax-m1  # Modelo gratuito disponible

# MT5 (forex/gold)
MT5_LOGIN=123456
MT5_PASSWORD=secret
MT5_SERVER=Broker-Demo

# Sistema
MODE=paper                       # "paper" | "live"
MAX_DAILY_LOSS_PCT=0.02

# Walk-Forward Validation
WFV_N_WINDOWS=6
WFV_TRAIN_BARS=3000              # ~31 días en M15
WFV_TEST_BARS=1000               # ~10 días en M15
WFV_STEP_BARS=1000               # desplazamiento entre ventanas
```

---

## Dependencias

```toml
[project]
name = "autoresearch-trading"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "MetaTrader5",          # data + ejecución forex/gold
    "vectorbt",             # backtesting vectorizado
    "pandas",
    "numpy",
    "ta-lib",               # indicadores técnicos
    "pandas-ta",
    "openai",               # cliente LLM (openrouter)
    "loguru",               # logging estructurado
    "sqlalchemy",           # ORM para SQLite
    "apscheduler",          # scheduling
    "python-dotenv",        # variables de entorno
    "psutil",               # monitoreo de recursos
    "rich",                 # output bonito en consola
]
```

---

## Hardware

- **GPU:** RTX 4060 Ti 16GB VRAM
- **RAM:** 32GB
- **CPU:** Intel i5-12400F
- **OS:** Windows (WSL2 o PowerShell)

---

## Diseño

Inspirado en [`karpathy/autoresearch`](https://github.com/karpathy/autoresearch), el sistema aplica los mismos principios al dominio de trading:

1. **Un único archivo modificable** — `strategy.py` es la única variable en el loop
2. **Métricas fijas** — `sharpe_wfv` es inmutable para comparaciones justas
3. **Tiempo fijo** — Backtest < 30s para iteración rápida (~120 experimentos/hora)
4. **Autonomía** — El agente corre indefinidamente sin preguntar

### Por qué Walk-Forward Validation

Un split estático 80/20 es frágil:
- La estrategia puede sobreajustar a un período específico
- No hay forma de saber si funcionará en datos futuros

WFV es más robusto:
- Evalúa la estrategia en múltiples ventanas temporales
- La penalización por varianza (`- 0.5 * std`) premia estrategias estables
- Más representativo del comportamiento real en producción

---

## Documentación Adicional

- [`agents.md`](agents.md) — Roles y responsabilidades del agente
- [`architecture.md`](architecture.md) — Arquitectura detallada del sistema
- [`autoresearch_trading_prompt_v2.md`](autoresearch_trading_prompt_v2.md) — Especificaciones técnicas completas
