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

    # Track 4 gets its own optional paper account — hackathon submissions
    # score each track independently, so once a real submission is being
    # prepared, Track 1's and Track 4's fills/P&L can't share one account.
    # Empty by default: falls back to the shared alpaca_api_key/secret_key
    # above (see get_alpaca_credentials), so local dev/testing with one
    # account needs zero config changes — only set these two once a second
    # paper account actually exists.
    alpaca_api_key_track4: str = ""
    alpaca_secret_key_track4: str = ""

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
    # Track 4 only: a cash-secured put's collateral (strike x 100) is posted
    # cash, not capital-at-risk the way Track 1's premium is — applying the
    # same 3% cap here blocks every symbol (even the cheapest, e.g. XLF at
    # $58/share is already 5.8% of a $100k account). See risk_gate.py.
    max_wheel_collateral_pct: float = 0.25


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_alpaca_credentials(track: str) -> tuple[str, str]:
    """Resolves which Alpaca paper account a track should trade against.
    Track 1 (and anything else) always uses the shared/default credentials;
    Track 4 uses its own pair once both are actually set in .env, otherwise
    falls back to the shared pair too — so testing with one account (today)
    and submission-time separation (once a second account exists) both work
    with zero code changes, only an .env edit."""
    settings = get_settings()
    if track == "track4_income_wheel" and settings.alpaca_api_key_track4 and settings.alpaca_secret_key_track4:
        return settings.alpaca_api_key_track4, settings.alpaca_secret_key_track4
    return settings.alpaca_api_key, settings.alpaca_secret_key
