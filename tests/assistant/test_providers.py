"""Phase 23, S23.1: provider abstraction (disabled-by-default, no network)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from assistant.providers import (
    ChatMessage,
    DisabledAssistant,
    OpenAICompatibleAssistant,
    build_provider,
)
from core.config import Config
from core.exceptions import AssistantError
from fakes import FakeHttpClient, HttpError


class PostingHttp(FakeHttpClient):
    """FakeHttpClient plus the ``post_json`` the provider relies on."""

    async def post_json(
        self,
        url: str,
        *,
        json_body: Any,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        status, _headers, body = await self._lookup(
            "POST", url, {"json": json_body, "headers": headers, "params": params}
        )
        if status >= 400:
            raise HttpError(status, url)
        return body


def _config(path: Path) -> Config:
    return Config(path / "settings.json", use_env=False)


def _enabled_config(path: Path) -> Config:
    cfg = _config(path)
    cfg.set("assistant.enabled", True)
    cfg.set("assistant.provider", "openai")
    cfg.set("assistant.base_url", "https://api.example.test/v1")
    cfg.set("assistant.model", "gpt-fake")
    cfg.set("assistant.api_key", "test-key-abc")
    return cfg


async def test_default_provider_is_disabled(tmp_path: Path) -> None:
    provider = build_provider(_config(tmp_path))
    assert isinstance(provider, DisabledAssistant)
    assert provider.enabled() is False
    with pytest.raises(AssistantError, match="disabled"):
        await provider.complete([ChatMessage(role="user", content="hi")])


def test_explicit_none_stays_disabled(tmp_path: Path) -> None:
    cfg = _enabled_config(tmp_path)
    cfg.set("assistant.provider", "none")
    assert isinstance(build_provider(cfg), DisabledAssistant)


def test_openai_requires_credentials(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    cfg.set("assistant.enabled", True)
    cfg.set("assistant.provider", "openai")
    provider = build_provider(cfg)
    assert isinstance(provider, OpenAICompatibleAssistant)
    assert provider.enabled() is False


def test_unknown_provider_raises(tmp_path: Path) -> None:
    cfg = _enabled_config(tmp_path)
    cfg.set("assistant.provider", "spooky")
    with pytest.raises(AssistantError, match="unknown assistant provider"):
        build_provider(cfg)


async def test_openai_posts_and_parses(tmp_path: Path) -> None:
    http = PostingHttp()
    http.stub(
        "https://api.example.test/v1/chat/completions",
        body={
            "choices": [{"message": {"content": "hello analyst"}}],
            "model": "gpt-x",
            "usage": {"prompt_tokens": 12, "completion_tokens": 3},
        },
    )
    provider = OpenAICompatibleAssistant(
        base_url="https://api.example.test/v1/",
        model="gpt-fake",
        api_key="test-key-abc",
        http=http,
    )
    assert provider.enabled() is True
    response = await provider.complete([ChatMessage(role="user", content="hi")])
    assert response.text == "hello analyst"
    assert response.provider == "openai"
    assert response.model == "gpt-x"
    assert response.usage["completion_tokens"] == 3

    request = http.requests[0]
    assert request["method"] == "POST"
    assert request["url"] == "https://api.example.test/v1/chat/completions"
    body: dict[str, Any] = request["kwargs"]["json"]
    assert body["model"] == "gpt-fake"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert body["max_tokens"] == 800
    headers: dict[str, Any] = request["kwargs"]["headers"]
    assert headers["Authorization"] == "Bearer test-key-abc"


async def test_openai_empty_message_content(tmp_path: Path) -> None:
    http = PostingHttp()
    http.stub(
        "https://api.example.test/v1/chat/completions",
        body={"choices": [{"message": {"content": None}}]},
    )
    provider = OpenAICompatibleAssistant(
        base_url="https://api.example.test/v1",
        model="m",
        api_key="test-key-abc",
        http=http,
    )
    response = await provider.complete([ChatMessage(role="user", content="hi")])
    assert response.text == ""
