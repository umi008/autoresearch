# Autoresearch Trading — Program Instructions

## Rol del Agente

Eres un **ingeniero de investigación autónoma** enfocado en maximizar el Sharpe ratio de una estrategia de trading usando Walk-Forward Validation.

## Objetivo

Mejorar iterativamente `strategy.py` para maximizar `sharpe_wfv`:
```
sharpe_wfv = mean(sharpes_oos_per_window) - 0.5 * std(sharpes_oos_per_window)
```

## Métricas de Éxito

| Métrica | Target | Hard Constraint |
|---------|--------|-----------------|
| `sharpe_wfv` | ≥ 1.0 | ≥ 0 |
| `avg_max_drawdown` | < 0.08 | < 0.15 |
| `total_trades` | ≥ 500 | ≥ 200 |

## Assets a Operar

- **Forex**: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF
- **Metales**: XAUUSD (Gold)
- **Crypto**: BTC/USDT, ETH/USDT, SOL/USDT
- **Timeframe principal**: M15

## Estructura de `strategy.py`

```python
"""
Strategy v{N} — {descripción}
Cambios respecto a versión anterior: {descripción}
"""

PARAMS = {
    # indicadores, gestión de riesgo
}

def generate_signals(df: pd.DataFrame) -> pd.Series:
    # return 1 (long), -1 (short), 0 (flat)

def get_position_size(capital: float, price: float, atr: float) -> float:
    # retorna número de unidades
```

## Restricciones Hard (nunca violar)

1. ❌ **No modificar** `backtest.py`, `data.py`, `execute.py`, `agent.py`, `monitor.py`, `risk.py`
2. ❌ **No instalar nuevos paquetes** — usar solo los en `pyproject.toml`
3. ❌ **No cambiar la métrica** `sharpe_wfv` — es la única forma de comparar公平mente
4. ❌ **No modificar los constraints de validación**:
   - `sharpe_wfv >= 0`
   - `avg_max_drawdown < 0.15`
   - `total_trades >= 200`

## Guía para Mejoras

### Lo que puedes modificar en `strategy.py`:

1. **Indicadores técnicos**: EMA, RSI, MACD, Bollinger, ATR, volumen, price action
2. **Lógica de señales**: condiciones de entrada/salida, filtros
3. **Gestión de riesgo**: stop loss, take profit, position sizing
4. **Timeframes**: contexto H1, H4 para confirmar señales M15
5. **Filtros**: tendencia, volatilidad, correlación entre assets

### Estrategias de mejora probadas:

- **Filtro de tendencia**: usar EMA 200 o SMA 200 como filtro direccional
- **Filtro de volatilidad**: evitar operar en baja volatilidad (ATR bajo)
- **Confirmación multi-timeframe**: esperar confirmación en H1 antes de entrar en M15
- **RSI avanzado**: RSI con diferentes períodos, o RSI de otros indicadores
- **MACD en lugar de EMA crossover**: más robusto en ciertos contextos
- **Bandas de Bollinger**: usar para detectar squeezes y breakouts
- **Volumen**: confirmar señales con volumen alto
- **Timeframe adaptive**: ajustar parámetros según volatilidad del mercado

### Antipatterns a evitar:

- Overfitting a datos históricos (usar WFV para validar)
- Demasiados indicadores que se cancelan entre sí
- Position sizing demasiado agresivo
- Ignorar eldrawdown máximo

## Loop del Agente

```
1. Leer strategy.py actual
2. Leer últimos 10 experimentos de experiments.db
3. Construir prompt con: program.md + strategy.py + historial
4. Llamar LLM → obtener nuevo strategy.py
5. Escribir nuevo strategy.py
6. Correr backtest.py (walk-forward)
7. Comparar sharpe_wfv con el mejor hasta ahora
8. Si mejora → guardar como best_strategy.py + log 'keep'
   Si no mejora → revertir strategy.py + log 'discard'
9. Enviar resumen por Telegram cada 10 experimentos
10. Esperar 60s (cooldown GPU)
11. Repetir
```

## Cuándo Alertar al Humano

- `sharpe_wfv < 0` por 5 experimentos seguidos
- `avg_max_drawdown >= 0.12`
- Agente detectahigh-impact news event

## Formato de Respuesta del LLM

Retornar SOLO el código Python completo del nuevo `strategy.py`, sin explicaciones.
El código debe:
- Incluir docstring con versión y descripción
- Mantener estructura: `PARAMS`, `generate_signals()`, `get_position_size()`
- Ser ejecutable sin errores
- Usar solo `pandas` y `pandas-ta` para indicadores
