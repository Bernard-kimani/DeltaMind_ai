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
    alpaca_mcp_server_path: str = "../alpaca-mcp-server"

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

    # Risk gate defaults (see app/agents/risk_gate.py)
    max_position_pct: float = 0.10
    max_margin_utilization_pct: float = 0.50
    stop_loss_pct: float = 0.20


@lru_cache
def get_settings() -> Settings:
    return Settings()
