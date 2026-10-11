"""Phase 23, S23.2/S23.3: assistant facade behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from assistant.providers import AssistantResponse, ChatMessage
from assistant.service import Assistant
from core.config import Config
from core.exceptions import AssistantError
from reports.builder import build_report


class FakeProvider:
    """Test double implementing the AssistantProvider protocol."""

    name = "fake"

    def __init__(self, *, text: str = "hello", error: str | None = None) -> None:
        self._text = text
        self._error = error
        self.messages: list[list[ChatMessage]] = []

    def enabled(self) -> bool:
        return True

    async def complete(self, messages: list[ChatMessage]) -> AssistantResponse:
        self.messages.append(messages)
        if self._error is not None:
            raise AssistantError(self._error)
        return AssistantResponse(text=self._text, provider=self.name, model="m-1")


class OffProvider:
    """Provider that reports disabled (mirrors a default config)."""

    name = "off"

    def enabled(self) -> bool:
        return False

    async def complete(self, messages: list[ChatMessage]) -> AssistantResponse:
        raise AssertionError("must not be called")


def _config(tmp_path: Path) -> Config:
    return Config(tmp_path / "settings.json", use_env=False)


def _model() -> Any:
    return build_report(
        {
            "id": 1,
            "uuid": "u-1",
            "mode": "quick",
            "status": "completed",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:00:01Z",
            "duration": 1.0,
            "error": None,
            "runs": [],
        },
        {"value": "example.com", "type": "domain"},
        [
            {
                "module": "dns",
                "title": "Open resolver",
                "severity": "medium",
                "confidence": 0.8,
                "data": {"port": 53},
                "evidence": "ref=1",
            }
        ],
    )


async def test_default_build_is_disabled(tmp_path: Path) -> None:
    assistant = Assistant(_config(tmp_path))
    assert assistant.enabled is False
    assert assistant.provider_name == "disabled"


async def test_disabled_returns_safe_answer(tmp_path: Path) -> None:
    assistant = Assistant(_config(tmp_path), provider=OffProvider())
    answer = await assistant.summarize(_model())
    assert answer.enabled is False
    assert answer.text == ""
    assert "disabled" in (answer.warning or "")


async def test_provider_seam_builds_from_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = FakeProvider(text="seamed")
    monkeypatch.setattr(
        "assistant.service.build_default_provider", lambda config, http=None: provider
    )
    assistant = Assistant(_config(tmp_path))
    assert assistant.enabled is True
    answer = await assistant.summarize(_model())
    assert answer.text == "seamed"


async def test_summarize_passthrough(tmp_path: Path) -> None:
    provider = FakeProvider(text="summary text")
    assistant = Assistant(_config(tmp_path), provider=provider)
    answer = await assistant.summarize(_model())
    assert answer.text == "summary text"
    assert answer.label == "AI-generated"
    assert answer.warning is None
    assert answer.provider == "fake"
    assert answer.model == "m-1"
    assert provider.messages[0][0].role == "system"


async def test_prompt_kinds_reach_provider(tmp_path: Path) -> None:
    provider = FakeProvider()
    assistant = Assistant(_config(tmp_path), provider=provider)
    await assistant.suggest_next_steps(_model())
    await assistant.explain({}, model=_model())
    await assistant.compare(_model(), _model())
    kinds = [
        " ".join(message.content for message in messages)
        for messages in provider.messages
    ]
    assert any("next steps" in kind for kind in kinds)
    assert any("Finding" in kind for kind in kinds)
    assert any("Earlier scan" in kind for kind in kinds)


async def test_provider_error_surfaces_as_warning(tmp_path: Path) -> None:
    provider = FakeProvider(error="boom from provider")
    assistant = Assistant(_config(tmp_path), provider=provider)
    answer = await assistant.summarize(_model())
    assert answer.enabled is False
    assert "boom from provider" in (answer.warning or "")


async def test_empty_text_warns(tmp_path: Path) -> None:
    provider = FakeProvider(text="   ")
    assistant = Assistant(_config(tmp_path), provider=provider)
    answer = await assistant.ask([ChatMessage(role="user", content="x")])
    assert "no text" in (answer.warning or "")
