"""Runtime configuration store for values the Controls UI can change live
(LLM provider/model/API keys, engine symbols/track/interval) — separate from
`.env`, which stays the source of truth for Alpaca credentials and the
initial/default LLM settings used when nobody's touched the UI yet (e.g. the
Day 1 hackathon deploy, run headless via scripts/run_agent_loop.py).

API keys are encrypted at rest with Windows DPAPI (bound to this Windows
user account — same approach as a sibling project's config manager) rather
than sitting in plaintext JSON on disk. Falls back to obfuscated-but-not-
secure storage with a loud warning off Windows, so the app doesn't crash in
that case, but this store is a local-dev convenience, not a portable secrets
system — production/live-loop deployment should use real env vars.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_STORE_PATH = Path(__file__).resolve().parent.parent / ".runtime_config.json"
_DPAPI_ENTROPY = b"DeltaMind_AI_config"

try:
    import base64

    import win32crypt

    def _encrypt(plaintext: str) -> str:
        blob = win32crypt.CryptProtectData(plaintext.encode("utf-8"), "DeltaMind AI secret", _DPAPI_ENTROPY, None, None, 0)
        return base64.b64encode(blob).decode("ascii")

    def _decrypt(encoded_blob: str) -> str:
        blob = base64.b64decode(encoded_blob)
        _, plaintext = win32crypt.CryptUnprotectData(blob, _DPAPI_ENTROPY, None, None, 0)
        return plaintext.decode("utf-8")

except ImportError:
    logger.warning("win32crypt unavailable — API keys in .runtime_config.json will NOT be encrypted at rest.")

    def _encrypt(plaintext: str) -> str:
        return plaintext

    def _decrypt(encoded_blob: str) -> str:
        return encoded_blob


def _defaults() -> dict[str, Any]:
    return {
        "llm": {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "temperature": "0.3",
            "featherless_api_key": settings.featherless_api_key,
            "fireworks_api_key": settings.fireworks_api_key,
        },
        "engine": {
            "symbols": "SPY,QQQ",
            "track": "track1_alpha_spreads",
            "interval_seconds": "300",
            "sentiment_threshold": "0.5",
            "volume_ratio_min": "1.2",
        },
    }


def _flatten(nested: dict[str, Any]) -> dict[str, Any]:
    return {
        "llm_provider": nested["llm"]["provider"],
        "llm_model": nested["llm"]["model"],
        "temperature": nested["llm"]["temperature"],
        "featherless_api_key": nested["llm"]["featherless_api_key"],
        "fireworks_api_key": nested["llm"]["fireworks_api_key"],
        "symbols": nested["engine"]["symbols"],
        "track": nested["engine"]["track"],
        "interval_seconds": nested["engine"]["interval_seconds"],
        "sentiment_threshold": nested["engine"]["sentiment_threshold"],
        "volume_ratio_min": nested["engine"]["volume_ratio_min"],
    }


def _unflatten(flat: dict[str, Any]) -> dict[str, Any]:
    return {
        "llm": {
            "provider": flat["llm_provider"],
            "model": flat["llm_model"],
            "temperature": flat["temperature"],
            "featherless_api_key": flat["featherless_api_key"],
            "fireworks_api_key": flat["fireworks_api_key"],
        },
        "engine": {
            "symbols": flat["symbols"],
            "track": flat["track"],
            "interval_seconds": flat["interval_seconds"],
            "sentiment_threshold": flat["sentiment_threshold"],
            "volume_ratio_min": flat["volume_ratio_min"],
        },
    }


def load() -> dict[str, Any]:
    if not _STORE_PATH.exists():
        return _flatten(_defaults())

    try:
        with open(_STORE_PATH, encoding="utf-8") as f:
            on_disk = json.load(f)
        nested = _defaults()
        nested["llm"].update(on_disk.get("llm", {}))
        nested["engine"].update(on_disk.get("engine", {}))

        for key in ("featherless_api_key", "fireworks_api_key"):
            encrypted = on_disk.get("llm", {}).get(f"{key}_encrypted")
            if encrypted:
                nested["llm"][key] = _decrypt(encrypted)

        return _flatten(nested)
    except Exception:
        logger.exception("Failed to load .runtime_config.json — falling back to defaults")
        return _flatten(_defaults())


def save(flat: dict[str, Any]) -> dict[str, Any]:
    nested = _unflatten(flat)
    on_disk = json.loads(json.dumps(nested))  # deep copy

    for key in ("featherless_api_key", "fireworks_api_key"):
        value = on_disk["llm"].pop(key, "")
        on_disk["llm"][f"{key}_encrypted"] = _encrypt(value) if value else ""

    with open(_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(on_disk, f, indent=2)

    return load()


def reset() -> dict[str, Any]:
    if _STORE_PATH.exists():
        os.remove(_STORE_PATH)
    return load()
