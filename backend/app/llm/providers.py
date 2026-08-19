"""Provider presets for the LLM client.

Featherless and Fireworks both expose OpenAI-compatible chat-completion
endpoints (incl. tool calling), so both are reachable through the same
`openai.OpenAI(base_url=...)` client — just swap base_url/api_key/model.
Anthropic is wired in separately since it uses its own SDK/wire format; it's
opt-in via LLM_PROVIDER=anthropic and NOT the default because it bills
separately from the Claude Code subscription (see PLAN.md).

Provider/model/API-key selection is sourced from app.config_store (the
Controls tab's "Save Changes"), which itself falls back to `.env` defaults
when nothing's been saved yet — so a headless Day-1 deploy that never
touches the UI still picks up sane values, and the live agent loop reflects
Controls tab changes on its very next cycle without a restart.

NOTE: verify exact model slugs against your Featherless/Fireworks dashboard —
provider catalogs change; the defaults in .env.example are best-effort.
"""

from dataclasses import dataclass

from app import config_store
from app.config import get_settings

settings = get_settings()

BASE_URLS = {
    "featherless": settings.featherless_base_url,
    "fireworks": settings.fireworks_base_url,
}


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str | None
    api_key: str
    model: str


def get_provider_config() -> ProviderConfig:
    flat = config_store.load()
    provider = flat["llm_provider"].lower()
    return build_provider_config(provider, flat["llm_model"], flat.get(f"{provider}_api_key", ""))


def build_provider_config(provider: str, model: str, api_key: str) -> ProviderConfig:
    """Construct a ProviderConfig from explicit values — used both by
    get_provider_config() (reads the saved config) and by the Controls tab's
    "Test API" button (tests values the user hasn't saved yet)."""
    provider = provider.lower()

    if provider in BASE_URLS:
        return ProviderConfig(name=provider, base_url=BASE_URLS[provider], api_key=api_key, model=model)
    if provider == "anthropic":
        return ProviderConfig(name="anthropic", base_url=None, api_key=api_key, model=model or "claude-sonnet-5")

    raise ValueError(f"Unknown LLM provider: {provider!r}")
