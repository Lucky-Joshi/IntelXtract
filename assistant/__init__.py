"""Phase 23 — optional, grounded AI assistant.

The assistant is **disabled by default**: nothing is sent off the machine
until the user opts in and supplies a provider. See :mod:`assistant.providers`.
"""

from __future__ import annotations

from assistant.providers import (
    AssistantProvider,
    AssistantResponse,
    ChatMessage,
    DisabledAssistant,
    OpenAICompatibleAssistant,
    build_provider,
)
from assistant.service import Assistant, AssistantAnswer

__all__ = [
    "Assistant",
    "AssistantAnswer",
    "AssistantProvider",
    "AssistantResponse",
    "ChatMessage",
    "DisabledAssistant",
    "OpenAICompatibleAssistant",
    "build_provider",
]
