"""Provider-agnostic LLM client used by every reasoning node (news_analyst,
lead_architect). Swap providers via LLM_PROVIDER without touching agent code.
"""

import json
import logging
import time

from app.llm import rate_limiter
from app.llm.providers import ProviderConfig, build_provider_config, get_provider_config

logger = logging.getLogger(__name__)

# Manual retry, not a library (e.g. tenacity): only 3 attempts, fixed
# backoff, and needs to catch different SDK-specific exception types per
# provider — not worth a new dependency for ~15 lines.
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = [1, 2, 4]


class LLMClient:
    def __init__(self, config) -> None:
        self.config = config
        if config.name == "anthropic":
            import anthropic

            self._client = anthropic.Anthropic(api_key=config.api_key)
        else:
            import openai

            self._client = openai.OpenAI(base_url=config.base_url, api_key=config.api_key)

    def _retryable_exceptions(self) -> tuple[type[Exception], ...]:
        if self.config.name == "anthropic":
            import anthropic

            return (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError)
        import openai

        return (openai.RateLimitError, openai.APIStatusError, openai.APIConnectionError)

    def _call_with_retry(self, fn):
        retryable = self._retryable_exceptions()
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                return fn()
            except retryable as exc:
                if attempt == _RETRY_ATTEMPTS - 1:
                    raise
                delay = _RETRY_BACKOFF_SECONDS[attempt]
                logger.warning("LLM call failed (%s), retrying in %ss (attempt %d/%d)", exc, delay, attempt + 1, _RETRY_ATTEMPTS)
                time.sleep(delay)

    def generate(self, system: str, user: str) -> str:
        rate_limiter.check_and_record()

        if self.config.name == "anthropic":
            resp = self._call_with_retry(lambda: self._client.messages.create(
                model=self.config.model,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user}],
            ))
            return resp.content[0].text

        resp = self._call_with_retry(lambda: self._client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        ))
        return resp.choices[0].message.content

    def structured_generate(self, system: str, user: str, schema: dict) -> dict:
        """Ask for a JSON object matching `schema` (field name -> python type) and parse it.

        Simple prompt-based structured output — swap for native tool/function
        calling once a specific provider's tool-calling reliability is confirmed.

        A successful HTTP call (handled by generate()'s own retry) can still
        return an empty or non-JSON body — confirmed live 2026-08-24: a
        Featherless call returned a completely empty string, and a bare
        `json.loads()` crashed the whole cycle for one symbol. That's a
        content-level failure, not a connection-level one, so it needs its
        own retry: request a fresh completion (not just re-parse the same
        empty string) up to _RETRY_ATTEMPTS times before giving up.
        """
        fields = ", ".join(f'"{k}": <{v.__name__}>' for k, v in schema.items())
        instruction = f"{system}\n\nRespond with ONLY a JSON object: {{{fields}}}"

        last_error: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            raw = self.generate(system=instruction, user=user)
            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                last_error = exc
                if attempt == _RETRY_ATTEMPTS - 1:
                    break
                delay = _RETRY_BACKOFF_SECONDS[attempt]
                logger.warning(
                    "structured_generate got non-JSON output (%r), retrying in %ss (attempt %d/%d)",
                    raw[:120], delay, attempt + 1, _RETRY_ATTEMPTS,
                )
                time.sleep(delay)

        raise ValueError(f"LLM never returned valid JSON after {_RETRY_ATTEMPTS} attempts") from last_error


def get_llm_client() -> LLMClient:
    """Not cached: provider/model/key can change via the Controls tab's Save
    Changes at any time, and constructing an SDK client is cheap relative to
    the network call each reasoning node is about to make anyway."""
    return LLMClient(get_provider_config())


def test_provider(provider: str, model: str, api_key: str) -> tuple[bool, str]:
    """Fires one minimal completion against explicit (possibly unsaved)
    provider/model/key values — backs the Controls tab's "Test API" button."""
    if not api_key:
        return False, "No API key provided"
    if not model:
        return False, "No model selected"

    try:
        config: ProviderConfig = build_provider_config(provider, model, api_key)
        client = LLMClient(config)
        reply = client.generate(system="Reply with exactly one word: OK", user="ping")
        return True, f"Connected — {config.name}/{config.model} replied: {reply.strip()[:60]!r}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
