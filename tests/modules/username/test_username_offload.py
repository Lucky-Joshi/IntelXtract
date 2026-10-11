"""Phase 25 (S25.4): username module loads its site registry off the loop."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from fakes import make_module_config, make_module_context
from modules.username import collector
from modules.username.collector import UsernameModule


async def test_site_registry_loaded_off_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loop_thread = threading.get_ident()
    seen: dict[str, int] = {}

    def spy(_config: Any) -> list[dict[str, Any]]:
        seen["thread"] = threading.get_ident()
        return []

    async def fake_check_sites(*args: Any, **kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr(collector, "load_sites", spy)
    monkeypatch.setattr(collector, "check_sites", fake_check_sites)

    ctx = make_module_context(make_module_config(tmp_path))
    result = await UsernameModule().run("@octocat", ctx)

    assert seen["thread"] != loop_thread
    assert result.data["probed"] == 0
