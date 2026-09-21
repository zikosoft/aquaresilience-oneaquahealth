"""AI provider abstraction: OpenAIProvider / AnthropicProvider + connection test.

Business rules (locked, see Master Spec section 9):
- provider/model/limits are configurable from Settings without code changes;
- once a key is saved, it is never returned to the frontend again;
- the API only ever reports a configured/not-configured state.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import httpx


class AIProvider(ABC):
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str]:
        """Returns (ok, message). Must never raise for expected failure modes."""


class OpenAIProvider(AIProvider):
    async def test_connection(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            if resp.status_code == 200:
                return True, "Connected to OpenAI successfully."
            if resp.status_code == 401:
                return False, "OpenAI rejected the API key (unauthorized)."
            return False, f"OpenAI returned an unexpected status ({resp.status_code})."
        except httpx.HTTPError as exc:
            return False, f"Could not reach OpenAI: {exc.__class__.__name__}."


class AnthropicProvider(AIProvider):
    async def test_connection(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.model or "claude-3-5-haiku-latest",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
            if resp.status_code in (200, 400):
                # 400 with a valid key still proves auth succeeded (e.g. bad model name);
                # only 401/403 indicate an authentication failure.
                return True, "Connected to Anthropic successfully."
            if resp.status_code in (401, 403):
                return False, "Anthropic rejected the API key (unauthorized)."
            return False, f"Anthropic returned an unexpected status ({resp.status_code})."
        except httpx.HTTPError as exc:
            return False, f"Could not reach Anthropic: {exc.__class__.__name__}."


def get_provider(provider_name: str, api_key: str, model: str) -> AIProvider:
    if provider_name == "openai":
        return OpenAIProvider(api_key=api_key, model=model)
    if provider_name == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model)
    raise ValueError(f"Unknown AI provider: {provider_name}")
