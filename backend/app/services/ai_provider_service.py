"""AI provider abstraction: OpenAIProvider / AnthropicProvider + connection
test + structured Situation Brief generation (P3).

Business rules (locked, see Master Spec section 9):
- provider/model/limits are configurable from Settings without code changes;
- once a key is saved, it is never returned to the frontend again;
- the API only ever reports a configured/not-configured state.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.settings import AIProviderConfig


def get_or_create_ai_config(db: Session) -> AIProviderConfig:
    """Singleton accessor: there is exactly one AI provider configuration
    row for this deployment (Master Spec — "shared scheduled analysis, one
    stored brief for all users" implies one shared provider config too)."""
    config = db.execute(select(AIProviderConfig)).scalars().first()
    if config is None:
        config = AIProviderConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


class AIProviderError(Exception):
    """Raised for any generation failure (auth, network, malformed response).
    Always caught by the caller (`intelligence_service.generate_situation_brief`)
    — an AI outage must never take down ingestion/risk/warnings (Master Spec
    §19 "graceful AI failure")."""


class AIProvider(ABC):
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str]:
        """Returns (ok, message). Must never raise for expected failure modes."""

    @abstractmethod
    async def generate_json(self, prompt: str, max_output_tokens: int) -> str:
        """Returns the raw text response, expected to be a single JSON
        object (possibly wrapped in prose/code fences — the caller is
        responsible for extraction and schema validation). Raises
        `AIProviderError` on any request/auth/network failure."""


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

    async def generate_json(self, prompt: str, max_output_tokens: int) -> str:
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": max_output_tokens,
                        "temperature": 0.2,
                        "response_format": {"type": "json_object"},
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Could not reach OpenAI: {exc.__class__.__name__}.") from exc

        if resp.status_code != 200:
            raise AIProviderError(f"OpenAI returned status {resp.status_code}: {resp.text[:300]}")
        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise AIProviderError(f"Unexpected OpenAI response shape: {exc}") from exc


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

    async def generate_json(self, prompt: str, max_output_tokens: int) -> str:
        # Anthropic's Messages API has no forced-JSON response mode like
        # OpenAI's `response_format`; the prompt itself instructs
        # "respond with ONLY the JSON object" and the caller
        # (`intelligence_service._extract_json`) tolerates surrounding
        # prose/code fences defensively either way.
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": max_output_tokens,
                        "temperature": 0.2,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Could not reach Anthropic: {exc.__class__.__name__}.") from exc

        if resp.status_code != 200:
            raise AIProviderError(f"Anthropic returned status {resp.status_code}: {resp.text[:300]}")
        try:
            return resp.json()["content"][0]["text"]
        except (KeyError, IndexError, ValueError) as exc:
            raise AIProviderError(f"Unexpected Anthropic response shape: {exc}") from exc


def get_provider(provider_name: str, api_key: str, model: str) -> AIProvider:
    if provider_name == "openai":
        return OpenAIProvider(api_key=api_key, model=model)
    if provider_name == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model)
    raise ValueError(f"Unknown AI provider: {provider_name}")
