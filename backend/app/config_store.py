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


# Each track watches a different universe, not one shared list: Track 4's
# wheel needs cheap-enough names for a CSP's collateral (strike x 100) to
# clear the 15%/25% sizing caps (verified live 2026-09-01 — INTC/BAC/DIS/
# PFE/KO/WMT/XLF/XLE all clear the real ~21-DTE/OI>=500/spread<=15% band),
# while Track 1/5's directional premium buys size off the premium itself
# (3% cap), so price level doesn't matter — they default to the original
# momentum/liquidity universe instead.
DEFAULT_TRACK = "track1_alpha_spreads"
_TRACK1_5_SYMBOLS = "SPY,QQQ,IWM,NVDA,AAPL,MSFT,AMZN,GOOGL,META,TSLA,AMD,COIN,XLF,XLE,SMH"
DEFAULT_SYMBOLS_BY_TRACK: dict[str, str] = {
    "track1_alpha_spreads": _TRACK1_5_SYMBOLS,
    "track4_income_wheel": "INTC,BAC,DIS,PFE,KO,WMT,XLF,XLE",
    "track5_momentum_swing": _TRACK1_5_SYMBOLS,
}


def _default_engine(track: str) -> dict[str, Any]:
    return {
        "symbols": DEFAULT_SYMBOLS_BY_TRACK.get(track, _TRACK1_5_SYMBOLS),
        "track": track,
        "interval_seconds": "300",
        "sentiment_threshold": "0.5",
        "volume_ratio_min": "1.2",
    }


def _defaults(track: str) -> dict[str, Any]:
    return {
        "llm": {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "temperature": "0.3",
            "featherless_api_key": settings.featherless_api_key,
            "fireworks_api_key": settings.fireworks_api_key,
        },
        "engines": {track: _default_engine(track)},
    }


def _flatten(nested: dict[str, Any], track: str) -> dict[str, Any]:
    engine = nested["engines"].get(track) or _default_engine(track)
    return {
        "llm_provider": nested["llm"]["provider"],
        "llm_model": nested["llm"]["model"],
        "temperature": nested["llm"]["temperature"],
        "featherless_api_key": nested["llm"]["featherless_api_key"],
        "fireworks_api_key": nested["llm"]["fireworks_api_key"],
        "symbols": engine["symbols"],
        "track": engine["track"],
        "interval_seconds": engine["interval_seconds"],
        "sentiment_threshold": engine["sentiment_threshold"],
        "volume_ratio_min": engine["volume_ratio_min"],
    }


def load(track: str = DEFAULT_TRACK) -> dict[str, Any]:
    if not _STORE_PATH.exists():
        return _flatten(_defaults(track), track)

    try:
        with open(_STORE_PATH, encoding="utf-8") as f:
            on_disk = json.load(f)
        nested = _defaults(track)
        nested["llm"].update(on_disk.get("llm", {}))

        # Deliberately no migration of an old pre-per-track-store single
        # "engine" key: it was shared across whichever track saved last, so
        # its "track" field is arbitrary, not a real ownership signal --
        # treating it as this-track's-saved-state is what caused Track 5 to
        # regress to Track 1's old "SPY,QQQ" default after this file split
        # per-track. Ignoring it means every track starts clean from its
        # own new curated default the first time post-deploy.
        on_disk_engines = on_disk.get("engines", {})

        if track in on_disk_engines:
            nested["engines"][track] = {**_default_engine(track), **on_disk_engines[track]}

        for key in ("featherless_api_key", "fireworks_api_key"):
            encrypted = on_disk.get("llm", {}).get(f"{key}_encrypted")
            if encrypted:
                nested["llm"][key] = _decrypt(encrypted)

        return _flatten(nested, track)
    except Exception:
        logger.exception("Failed to load .runtime_config.json — falling back to defaults")
        return _flatten(_defaults(track), track)


def save(flat: dict[str, Any], track: str = DEFAULT_TRACK) -> dict[str, Any]:
    on_disk: dict[str, Any] = {}
    if _STORE_PATH.exists():
        try:
            with open(_STORE_PATH, encoding="utf-8") as f:
                on_disk = json.load(f)
        except Exception:
            logger.exception("Failed to read existing .runtime_config.json before save — overwriting")

    llm_out = {
        "provider": flat["llm_provider"],
        "model": flat["llm_model"],
        "temperature": flat["temperature"],
    }
    for key in ("featherless_api_key", "fireworks_api_key"):
        value = flat.get(key, "")
        llm_out[f"{key}_encrypted"] = _encrypt(value) if value else ""

    engines_out = on_disk.get("engines", {})
    engines_out[track] = {
        "symbols": flat["symbols"],
        "track": flat["track"],
        "interval_seconds": flat["interval_seconds"],
        "sentiment_threshold": flat["sentiment_threshold"],
        "volume_ratio_min": flat["volume_ratio_min"],
    }

    with open(_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump({"llm": llm_out, "engines": engines_out}, f, indent=2)

    return load(track)


def reset(track: str = DEFAULT_TRACK) -> dict[str, Any]:
    if not _STORE_PATH.exists():
        return load(track)
    try:
        with open(_STORE_PATH, encoding="utf-8") as f:
            on_disk = json.load(f)
        on_disk.get("engines", {}).pop(track, None)
        with open(_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(on_disk, f, indent=2)
    except Exception:
        logger.exception("Failed to reset %s in .runtime_config.json", track)
    return load(track)
