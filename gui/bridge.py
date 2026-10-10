"""Qt ↔ asyncio engine bridge.

A dedicated ``QThread`` hosts the asyncio event loop that drives
:class:`~core.engine.ScanEngine`. Progress and results cross into the Qt
main thread through queued signals (S5.12).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.config import Config
from core.engine import ModuleRun, ScanEngine, ScanModule
from core.logger import get_logger
from database.connection import Database
from database.migrations import migrate
from database.persistence import make_result_sink

_log = get_logger(__name__)


class EngineBridge(QObject):
    """Runs scans on a worker thread and re-emits progress as Qt signals."""

    scan_started = Signal(str, str)
    module_finished = Signal(dict)
    scan_finished = Signal(dict)
    scan_failed = Signal(str)
    modules_ready = Signal(list)

    _run_request = Signal(str, str, object)
    _modules_request = Signal()

    def __init__(
        self,
        config: Config,
        *,
        db_path: str | None = None,
        modules: Sequence[ScanModule] | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._db_path = (
            db_path
            if db_path is not None
            else str(config.get("paths.db_path", ":memory:"))
        )
        self._modules = list(modules or ())
        self._engine: ScanEngine | None = None
        self._db: Database | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._run_request.connect(self._handle_scan)
        self._modules_request.connect(self._handle_modules)
        self._thread.start()

    @property
    def db_path(self) -> str:
        """Resolved database path used by scans."""
        return self._db_path

    def request_scan(
        self,
        target: str,
        mode: str = "quick",
        module_names: Sequence[str] | None = None,
    ) -> None:
        """Queue a scan; completion arrives via the result signals."""
        names = list(module_names) if module_names is not None else None
        self._run_request.emit(target, mode, names)

    def request_modules(self) -> None:
        """Ask the worker thread for registered module names."""
        self._modules_request.emit()

    def shutdown(self) -> None:
        """Stop the worker thread, close the database, then the asyncio loop."""
        self._thread.quit()
        self._thread.wait(5000)
        loop = self._loop
        if loop is not None and not loop.is_closed():
            if self._db is not None:
                try:
                    loop.run_until_complete(self._db.close())
                except Exception:  # pragma: no cover - defensive cleanup
                    _log.exception("failed to close engine bridge database")
            loop.close()
        self._db = None
        self._loop = None

    @Slot(str, str, object)
    def _handle_scan(self, target: str, mode: str, module_names: object) -> None:
        self.scan_started.emit(target, mode)
        names = list(module_names) if isinstance(module_names, list) else None
        try:
            engine = self._ensure_engine()
            loop = self._ensure_loop()
            result = loop.run_until_complete(
                engine.scan(target, mode=mode, module_names=names)
            )
        except Exception as exc:
            _log.exception("scan failed in engine bridge")
            self.scan_failed.emit(str(exc))
            return
        self.scan_finished.emit(result.to_dict())

    @Slot()
    def _handle_modules(self) -> None:
        try:
            names = self._ensure_engine().module_names()
        except Exception:
            _log.exception("module discovery failed")
            names = []
        self.modules_ready.emit(names)

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        return self._loop

    def _ensure_engine(self) -> ScanEngine:
        if self._engine is None:
            loop = self._ensure_loop()
            raw = self._db_path
            path = ":memory:" if raw == ":memory:" else str(Path(raw).expanduser())
            self._db = Database(path)
            loop.run_until_complete(self._db.connect())
            loop.run_until_complete(migrate(self._db))
            self._engine = ScanEngine(
                self._config,
                modules=self._modules,
                result_sink=make_result_sink(self._db),
                on_module_done=self._forward_module,
            )
        return self._engine

    def _forward_module(self, run: ModuleRun) -> None:
        """Engine module-done seam; emits into the Qt main thread."""
        self.module_finished.emit(run.to_dict())
