"""Provider-agnostic LLM client used by every reasoning node (news_analyst,
lead_architect). Swap providers via LLM_PROVIDER without touching agent code.
"""

import json

from app.llm.providers import ProviderConfig, build_provider_config, get_provider_config


class LLMClient:
    def __init__(self, config) -> None:
        self.config = config
        if config.name == "anthropic":
            import anthropic

            self._client = anthropic.Anthropic(api_key=config.api_key)
        else:
            import openai

            self._client = openai.OpenAI(base_url=config.base_url, api_key=config.api_key)

    def generate(self, system: str, user: str) -> str:
        if self.config.name == "anthropic":
            resp = self._client.messages.create(
                model=self.config.model,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return resp.content[0].text

        resp = self._client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content

    def structured_generate(self, system: str, user: str, schema: dict) -> dict:
        """Ask for a JSON object matching `schema` (field name -> python type) and parse it.

        Simple prompt-based structured output — swap for native tool/function
        calling once a specific provider's tool-calling reliability is confirmed.
        """
        fields = ", ".join(f'"{k}": <{v.__name__}>' for k, v in schema.items())
        instruction = f"{system}\n\nRespond with ONLY a JSON object: {{{fields}}}"
        raw = self.generate(system=instruction, user=user)
        return json.loads(raw)


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
