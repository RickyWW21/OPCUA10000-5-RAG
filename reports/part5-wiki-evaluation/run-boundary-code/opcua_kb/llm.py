"""Small standard-library OpenAI-compatible chat completion client."""

from __future__ import annotations

import json
import os
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMError(RuntimeError):
    """Raised when an LLM request cannot be completed or parsed."""


class ChatModel(Protocol):
    def generate(self, *, system: str, user: str, temperature: float = 0.0) -> str:
        ...


Transport = Callable[[Request, float], bytes]


def _default_transport(request: Request, timeout: float) -> bytes:
    with urlopen(request, timeout=timeout) as response:
        return response.read()


class OpenAICompatibleChatModel:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        timeout: float = 60.0,
        transport: Transport | None = None,
    ) -> None:
        key = api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not key:
            raise LLMError("LLM API key is required")
        if not model:
            raise LLMError("LLM model is required")
        if timeout <= 0:
            raise LLMError("LLM timeout must be positive")
        endpoint = base_url.rstrip("/")
        if not endpoint:
            raise LLMError("LLM base URL is required")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        self.api_key = key
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout
        self._transport = transport or _default_transport

    def generate(self, *, system: str, user: str, temperature: float = 0.0) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            raw = self._transport(request, self.timeout)
        except HTTPError as exc:
            raise LLMError(f"LLM request failed with HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise LLMError("LLM request failed") from exc
        try:
            document = json.loads(raw.decode("utf-8"))
            content = document["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content:
                raise TypeError
            return content
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM response had an invalid schema") from exc
