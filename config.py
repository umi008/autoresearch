"""
Configuración del sistema Autoresearch Trading.
Carga credenciales y variables de entorno desde .env.

Usage:
    from config import config
    print(config.LLM_MODEL)
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Cargar .env desde el directorio del proyecto
_project_root = Path(__file__).parent
load_dotenv(_project_root / ".env")


@dataclass
class LLMConfig:
    """Configuración del proveedor LLM."""
    provider: Literal["ollama", "openrouter"] = "ollama"
    base_url: str = "http://localhost:11434/v1"
    model: str = "deepseek-r1:14b"
    api_key: str | None = None

    def validate(self) -> list[str]:
        errors = []
        if self.provider == "openrouter" and not self.api_key:
            errors.append("OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter")
        if self.provider == "ollama":
            # ollama no requiere API key pero sí el servidor corriendo
            if not self.base_url:
                errors.append("OLLAMA_BASE_URL is required when LLM_PROVIDER=ollama")
        return errors


@dataclass
class MT5Config:
    """Configuración de MetaTrader 5."""
    login: int | None = None
    password: str | None = None
    server: str | None = None

    @property
    def is_configured(self) -> bool:
        return all([self.login, self.password, self.server])

    def validate(self) -> list[str]:
        errors = []
        if not self.is_configured:
            errors.append("MT5 credentials not fully configured (MT5_LOGIN, MT5_PASSWORD, MT5_SERVER)")
        return errors


@dataclass
class BinanceConfig:
    """Configuración de Binance/CCXT."""
    api_key: str | None = None
    secret: str | None = None
    testnet: bool = True

    @property
    def is_configured(self) -> bool:
        return all([self.api_key, self.secret])

    def validate(self) -> list[str]:
        errors = []
        if not self.is_configured:
            errors.append("BINANCE_API_KEY and BINANCE_SECRET are required for crypto trading")
        return errors


@dataclass
class BybitConfig:
    """Configuración de Bybit (alternativa a Binance)."""
    api_key: str | None = None
    secret: str | None = None
    testnet: bool = True

    @property
    def is_configured(self) -> bool:
        return all([self.api_key, self.secret])

    def validate(self) -> list[str]:
        errors = []
        if not self.is_configured:
            errors.append("BYBIT_API_KEY and BYBIT_SECRET not configured")
        return errors


@dataclass
class TelegramConfig:
    """Configuración de Telegram para alertas."""
    bot_token: str | None = None
    chat_id: str | None = None

    @property
    def is_configured(self) -> bool:
        return all([self.bot_token, self.chat_id])

    def validate(self) -> list[str]:
        errors = []
        if not self.is_configured:
            errors.append("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID not configured (alertas deshabilitadas)")
        return errors


@dataclass
class WFVConfig:
    """Configuración de Walk-Forward Validation."""
    n_windows: int = 6
    train_bars: int = 3000
    test_bars: int = 1000
    step_bars: int = 1000

    def validate(self) -> list[str]:
        errors = []
        if self.n_windows < 1:
            errors.append("WFV_N_WINDOWS must be >= 1")
        if self.train_bars < 100:
            errors.append("WFV_TRAIN_BARS must be >= 100")
        if self.test_bars < 50:
            errors.append("WFV_TEST_BARS must be >= 50")
        if self.step_bars < 100:
            errors.append("WFV_STEP_BARS must be >= 100")
        return errors


@dataclass
class SystemConfig:
    """Configuración general del sistema."""
    mode: Literal["paper", "live"] = "paper"
    max_daily_loss_pct: float = 0.02

    def validate(self) -> list[str]:
        errors = []
        if self.mode not in ["paper", "live"]:
            errors.append(f"MODE must be 'paper' or 'live', got '{self.mode}'")
        if not 0 < self.max_daily_loss_pct < 1:
            errors.append(f"MAX_DAILY_LOSS_PCT must be between 0 and 1, got {self.max_daily_loss_pct}")
        return errors


@dataclass
class Config:
    """Configuración completa del sistema."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    mt5: MT5Config = field(default_factory=MT5Config)
    binance: BinanceConfig = field(default_factory=BinanceConfig)
    bybit: BybitConfig = field(default_factory=BybitConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    wfv: WFVConfig = field(default_factory=WFVConfig)
    system: SystemConfig = field(default_factory=SystemConfig)

    @classmethod
    def from_env(cls) -> "Config":
        """Carga configuración desde variables de entorno."""
        return cls(
            llm=LLMConfig(
                provider=os.getenv("LLM_PROVIDER", "ollama"),
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                model=os.getenv("LLM_MODEL", "deepseek-r1:14b"),
                api_key=os.getenv("OPENROUTER_API_KEY"),
            ),
            mt5=MT5Config(
                login=int(os.getenv("MT5_LOGIN", "0")) or None,
                password=os.getenv("MT5_PASSWORD"),
                server=os.getenv("MT5_SERVER"),
            ),
            binance=BinanceConfig(
                api_key=os.getenv("BINANCE_API_KEY"),
                secret=os.getenv("BINANCE_SECRET"),
                testnet=os.getenv("BINANCE_TESTNET", "true").lower() == "true",
            ),
            bybit=BybitConfig(
                api_key=os.getenv("BYBIT_API_KEY"),
                secret=os.getenv("BYBIT_SECRET"),
                testnet=os.getenv("BYBIT_TESTNET", "true").lower() == "true",
            ),
            telegram=TelegramConfig(
                bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
                chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            ),
            wfv=WFVConfig(
                n_windows=int(os.getenv("WFV_N_WINDOWS", "6")),
                train_bars=int(os.getenv("WFV_TRAIN_BARS", "3000")),
                test_bars=int(os.getenv("WFV_TEST_BARS", "1000")),
                step_bars=int(os.getenv("WFV_STEP_BARS", "1000")),
            ),
            system=SystemConfig(
                mode=os.getenv("MODE", "paper"),
                max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", "0.02")),
            ),
        )

    def validate(self) -> list[str]:
        """Valida toda la configuración. Retorna lista de errores."""
        errors = []
        errors.extend(self.llm.validate())
        errors.extend(self.mt5.validate())
        errors.extend(self.binance.validate())
        errors.extend(self.bybit.validate())
        errors.extend(self.telegram.validate())
        errors.extend(self.wfv.validate())
        errors.extend(self.system.validate())
        return errors


# Instancia global de configuración
config = Config.from_env()


def validate_config() -> None:
    """
    Valida la configuración. Lanza ValueError si hay errores críticos.
    Los warnings (ej. Telegram no configurado) solo se imprimen, no lanzan errores.
    """
    errors = config.validate()

    critical_errors = []
    warnings = []

    for error in errors:
        # Telegram es opcional, otros son críticos
        if "TELEGRAM" in error:
            warnings.append(f"WARNING: {error}")
        else:
            critical_errors.append(error)

    for warning in warnings:
        print(f"\033[93m{warning}\033[0m")  # Yellow

    if critical_errors:
        error_msg = "\n".join([f"ERROR: {e}" for e in critical_errors])
        raise ValueError(f"Configuración inválida:\n{error_msg}")


# Validar al importar (puede desactivarse si se necesita carga lazy)
try:
    validate_config()
except ValueError as e:
    # Si .env no existe todavía, no lanzar error - permitir uso con defaults
    if "Configuración inválida" not in str(e):
        raise
