"""Assistant providers (Phase 23, S23.1).

The assistant is opt-in and **disabled by default**. :class:`DisabledAssistant`
is inert — it makes no network call, so no report content leaves the machine.

The only non-disabled backend is :class:`OpenAICompatibleAssistant`: a generic
chat-completions client that works with any OpenAI-compatible endpoint (the
user supplies ``base_url``, ``model``, and an API key). No vendor SDK is
required; the request rides the shared :class:`~core.http_client.HttpClient`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from core.config import Config
from core.exceptions import AssistantError
from core.http_client import HttpClient

CHAT_COMPLETIONS_PATH = "/chat/completions"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One chat message (``system``/``user``/``assistant``)."""

    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True, slots=True)
class AssistantResponse:
    """Text returned by a provider plus provenance metadata."""

    text: str
    provider: str
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class AssistantProvider(Protocol):
    """Minimal provider contract consumed by :class:`assistant.Assistant`."""

    name: str

    def enabled(self) -> bool:
        """Whether this provider is configured and allowed to run."""
        ...

    async def complete(self, messages: list[ChatMessage]) -> AssistantResponse:
        """Return a completion for ``messages``."""
        ...


class DisabledAssistant:
    """Inert default provider; makes no network calls."""

    name = "disabled"

    def enabled(self) -> bool:
        return False

    async def complete(self, messages: list[ChatMessage]) -> AssistantResponse:
        raise AssistantError(
            "AI assistant is disabled; enable assistant.enabled and configure a "
            "provider to send report content off this machine"
        )


class OpenAICompatibleAssistant:
    """Chat-completions client for any OpenAI-compatible endpoint."""

    name = "openai"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        timeout: float = 60.0,
        max_tokens: int = 800,
        temperature: float = 0.0,
        http: Any = None,
    ) -> None:
        self._base_url = base_url.strip()
        self._model = model.strip()
        self._api_key = api_key.strip()
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._http = http if http is not None else HttpClient(timeout=timeout)

    def enabled(self) -> bool:
        """Only enabled with a base URL, model, and API key configured."""
        return bool(self._base_url and self._model and self._api_key)

    async def complete(self, messages: list[ChatMessage]) -> AssistantResponse:
        if not self.enabled():
            raise AssistantError("openai provider needs a base_url, model, and api_key")
        url = self._base_url.rstrip("/") + CHAT_COMPLETIONS_PATH
        payload = {
            "model": self._model,
            "messages": [message.to_dict() for message in messages],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        data = await self._http.post_json(
            url,
            json_body=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        if not isinstance(data, dict):
            raise AssistantError("assistant provider returned a non-object response")
        choices = data.get("choices")
        text = ""
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            if isinstance(message, dict):
                text = str(message.get("content") or "")
        usage = data.get("usage")
        return AssistantResponse(
            text=text,
            provider=self.name,
            model=str(data.get("model") or self._model),
            usage=dict(usage) if isinstance(usage, dict) else {},
        )


def build_provider(config: Config, *, http: Any = None) -> AssistantProvider:
    """Construct the configured provider; disabled unless explicitly opted in."""
    if not bool(config.get("assistant.enabled", False)):
        return DisabledAssistant()
    provider = str(config.get("assistant.provider", "disabled")).strip().lower()
    if provider in ("", "disabled", "none"):
        return DisabledAssistant()
    if provider in ("openai", "openai-compatible"):
        return OpenAICompatibleAssistant(
            base_url=str(config.get("assistant.base_url", "")),
            model=str(config.get("assistant.model", "")),
            api_key=str(config.get("assistant.api_key", "")),
            timeout=float(config.get("assistant.timeout", 60.0)),
            max_tokens=int(config.get("assistant.max_tokens", 800)),
            temperature=float(config.get("assistant.temperature", 0.0)),
            http=http,
        )
    raise AssistantError(f"unknown assistant provider: {provider!r}")


__all__ = [
    "AssistantProvider",
    "AssistantResponse",
    "ChatMessage",
    "DisabledAssistant",
    "OpenAICompatibleAssistant",
    "build_provider",
]
