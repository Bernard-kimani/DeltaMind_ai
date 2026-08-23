from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Alpaca
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = True
    alpaca_trade_api_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_api_url: str = "https://data.alpaca.markets"

    # LLM
    llm_provider: str = "featherless"
    llm_model: str = "moonshotai/Kimi-K2-Instruct"
    llm_fallback_model: str = "deepseek-ai/DeepSeek-V3"
    featherless_api_key: str = ""
    featherless_base_url: str = "https://api.featherless.ai/v1"
    fireworks_api_key: str = ""
    fireworks_base_url: str = "https://api.fireworks.ai/inference/v1"
    anthropic_api_key: str = ""

    # Database
    database_url: str = "sqlite:///./deltamind.db"

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    backend_cors_origins: str = "http://localhost:5173"

    # Risk gate defaults (see app/agents/risk_gate.py). "Balanced" posture,
    # chosen with the user over "Conservative" (2%/4/60%/15%) and
    # "Aggressive" (5%/8/50%/15%) — the middle of their own researched range.
    max_position_pct: float = 0.03
    max_margin_utilization_pct: float = 0.50
    stop_loss_pct: float = 0.20
    max_open_positions: int = 6
    min_cash_reserve_pct: float = 0.55
    max_sector_pct: float = 0.15


@lru_cache
def get_settings() -> Settings:
    return Settings()
