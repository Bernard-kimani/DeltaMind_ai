from fastapi import APIRouter
from pydantic import BaseModel

from app import config_store, watchlist
from app.alpaca.rest_client import test_connection as test_alpaca_connection
from app.config import get_alpaca_credentials
from app.llm.client import test_provider

router = APIRouter()


class FlatConfig(BaseModel):
    llm_provider: str
    llm_model: str
    featherless_api_key: str = ""
    fireworks_api_key: str = ""
    # True only for an explicit "Clear Key" action from the Controls tab --
    # a blank featherless_api_key/fireworks_api_key above just means "the
    # user didn't touch this field" (see get_config's redaction below, which
    # is why the field always loads blank) and leaves the stored key alone.
    clear_featherless_key: bool = False
    clear_fireworks_key: bool = False
    temperature: str = "0.3"
    symbols: str = "SPY,QQQ"
    track: str = "track1_alpha_spreads"
    interval_seconds: str = "300"
    sentiment_threshold: str = "0.5"
    volume_ratio_min: str = "1.2"


class TestLLMRequest(BaseModel):
    provider: str
    model: str
    api_key: str


def _redact(cfg: dict) -> dict:
    """Never let a saved API key reach the browser -- `GET /api/config` is a
    public, unauthenticated endpoint on the live demo deploy, so returning
    the real value here would let anyone curl it straight out of the JSON
    response regardless of the Controls tab's password-masked input (that
    only hides it visually once it's already in the page). The frontend
    gets a boolean instead so it can show "a key is configured" without
    ever holding the actual value."""
    return {
        **cfg,
        "featherless_api_key": "",
        "fireworks_api_key": "",
        "featherless_api_key_set": bool(cfg.get("featherless_api_key")),
        "fireworks_api_key_set": bool(cfg.get("fireworks_api_key")),
    }


@router.get("")
def get_config(track: str = "track1_alpha_spreads") -> dict:
    return _redact(config_store.load(track))


@router.post("")
def save_config(body: FlatConfig) -> dict:
    saved = config_store.save(
        body.model_dump(), body.track,
        clear_featherless_key=body.clear_featherless_key,
        clear_fireworks_key=body.clear_fireworks_key,
    )
    return _redact(saved)


@router.post("/reset")
def reset_config(track: str = "track1_alpha_spreads") -> dict:
    return _redact(config_store.reset(track))


@router.post("/test-llm")
def test_llm(body: TestLLMRequest) -> dict:
    ok, message = test_provider(body.provider, body.model, body.api_key)
    return {"ok": ok, "message": message}


@router.post("/test-alpaca")
def test_alpaca(track: str = "track1_alpha_spreads") -> dict:
    """`track` picks which account to test — Track 4 gets its own once
    ALPACA_API_KEY_TRACK4/ALPACA_SECRET_KEY_TRACK4 are set in .env (see
    get_alpaca_credentials); until then this resolves to the same shared
    account either track would pass, so testing Track 1's button today
    behaves exactly as before."""
    api_key, secret_key = get_alpaca_credentials(track)
    ok, message = test_alpaca_connection(api_key, secret_key)
    return {"ok": ok, "message": message}


@router.get("/watchlist")
def get_watchlist() -> dict:
    """Backs the Controls tab's "Load curated watchlist" button — the
    ~15-symbol categorized universe from app/watchlist.py, as a
    comma-separated string matching the Symbols field's own format."""
    return {"csv": watchlist.as_csv(), "categories": watchlist.WATCHLIST_CATEGORIES}
