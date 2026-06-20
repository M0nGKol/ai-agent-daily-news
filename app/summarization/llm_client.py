"""OpenAI-compatible LLM client for summarization."""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Mapping
from urllib import request
from urllib.error import HTTPError, URLError

from app.summarization.utils import clean_text, read_config_value

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_LLM_MODEL = "gpt-4o-mini"


class OpenAICompatibleClient:
    """Small OpenAI-compatible chat completions client."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_OPENAI_BASE_URL,
        timeout_seconds: float = 20.0,
        urlopen: Callable[..., Any] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._urlopen = urlopen or request.urlopen

    def complete(self, prompt: str) -> str:
        """Call an OpenAI-compatible chat completions endpoint."""

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You summarize AI technology sources using only the "
                        "provided source fields. Return strict JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self._urlopen(req, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("LLM summarization request failed") from exc

        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM summarization response was missing content") from exc


def build_configured_llm_client(
    config: Mapping[str, Any] | object | None = None,
) -> OpenAICompatibleClient | None:
    """Create an OpenAI-compatible client only when provider and API key exist."""

    if config is None:
        provider = os.getenv("LLM_PROVIDER")
        api_key = os.getenv("LLM_API_KEY")
        model = os.getenv("LLM_MODEL") or DEFAULT_LLM_MODEL
        base_url = os.getenv("LLM_BASE_URL") or os.getenv("LLM_API_BASE_URL")
    else:
        provider = read_config_value(config, "LLM_PROVIDER")
        api_key = read_config_value(config, "LLM_API_KEY")
        model = read_config_value(config, "LLM_MODEL") or DEFAULT_LLM_MODEL
        base_url = read_config_value(config, "LLM_BASE_URL") or read_config_value(
            config, "LLM_API_BASE_URL"
        )

    provider = clean_text(provider).lower()
    api_key = clean_text(api_key)
    model = clean_text(model)
    if not provider or not api_key or not model:
        return None

    resolved_base_url = _resolve_base_url(provider, base_url)
    if resolved_base_url is None:
        return None

    return OpenAICompatibleClient(
        api_key=api_key,
        model=model,
        base_url=resolved_base_url,
    )


def _resolve_base_url(provider: str, configured_base_url: Any) -> str | None:
    base_url = clean_text(configured_base_url)
    if base_url:
        return base_url.rstrip("/")
    if provider in {"openai", "openai-compatible"}:
        return DEFAULT_OPENAI_BASE_URL
    if provider.startswith("http://") or provider.startswith("https://"):
        return provider.rstrip("/")
    return None
