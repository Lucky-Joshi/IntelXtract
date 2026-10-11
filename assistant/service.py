"""Assistant facade (Phase 23, S23.2/S23.3).

Binds a provider to the grounding prompt templates and always labels output as
AI-generated. When the assistant is disabled, :meth:`Assistant.ask` returns a
disabled answer without touching the network or the provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from assistant import prompts, providers
from assistant.providers import AssistantProvider, ChatMessage
from core.config import Config
from core.exceptions import AssistantError
from reports.builder import ReportModel

DISABLED_WARNING = (
    "AI assistant is disabled (opt-in). Set assistant.enabled=true and "
    "configure a provider to send report content off this machine."
)

LABEL = "AI-generated"


def build_default_provider(config: Config, *, http: Any = None) -> AssistantProvider:
    """Provider factory seam (patched in tests)."""
    return providers.build_provider(config, http=http)


@dataclass(frozen=True, slots=True)
class AssistantAnswer:
    """AI-generated text plus provenance and safety metadata."""

    text: str
    provider: str
    model: str = ""
    label: str = LABEL
    enabled: bool = True
    warning: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "label": self.label,
            "enabled": self.enabled,
            "warning": self.warning,
            "usage": self.usage,
        }


class Assistant:
    """High-level assistant: provider + grounding prompts + safe defaults."""

    def __init__(
        self,
        config: Config,
        *,
        provider: AssistantProvider | None = None,
        http: Any = None,
    ) -> None:
        self._config = config
        self._provider = (
            provider
            if provider is not None
            else build_default_provider(config, http=http)
        )

    @property
    def enabled(self) -> bool:
        """Whether a live provider is configured."""
        return self._provider.enabled()

    @property
    def provider_name(self) -> str:
        """Name of the active provider."""
        return self._provider.name

    async def ask(self, messages: list[ChatMessage]) -> AssistantAnswer:
        """Send ``messages`` to the provider and label the result."""
        if not self._provider.enabled():
            return AssistantAnswer(
                text="",
                provider=self._provider.name,
                enabled=False,
                warning=DISABLED_WARNING,
            )
        try:
            response = await self._provider.complete(messages)
        except AssistantError as exc:
            return AssistantAnswer(
                text="",
                provider=self._provider.name,
                enabled=False,
                warning=str(exc),
            )
        text = response.text.strip()
        warning = None if text else "The assistant returned no text."
        return AssistantAnswer(
            text=text,
            provider=response.provider,
            model=response.model,
            enabled=True,
            warning=warning,
            usage=response.usage,
        )

    async def summarize(self, model: ReportModel) -> AssistantAnswer:
        """Executive summary of a scan."""
        return await self.ask(prompts.summarize_messages(model))

    async def suggest_next_steps(self, model: ReportModel) -> AssistantAnswer:
        """Grounded defensive next steps for a scan."""
        return await self.ask(prompts.next_steps_messages(model))

    async def explain(
        self, finding: Any, *, model: ReportModel | None = None
    ) -> AssistantAnswer:
        """Plain-language explanation of a single finding."""
        return await self.ask(prompts.explain_messages(finding, model))

    async def compare(self, before: ReportModel, after: ReportModel) -> AssistantAnswer:
        """Compare an earlier and a later scan of the same target."""
        return await self.ask(prompts.compare_messages(before, after))


__all__ = [
    "DISABLED_WARNING",
    "LABEL",
    "Assistant",
    "AssistantAnswer",
    "build_default_provider",
]
