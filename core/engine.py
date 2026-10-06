"""Scan engine facade: input -> plan -> queue -> pool -> structured results.

Phase 2 wires the pipeline together; the input classifier (Phase 6), module
contract (Phase 7), and persistence (Phase 3) plug into the seams exposed
here (``classifier``, ``result_sink``, registered modules).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from core.cache import AsyncTTLCache
from core.config import Config
from core.constants import ModuleStatus, ScanMode, ScanStatus, TargetType, TaskState
from core.exceptions import ScanError, TaskTimeoutError, ValidationError
from core.logger import get_logger, scan_context
from core.scheduler import TaskScheduler
from core.worker_pool import WorkerPool

_log = get_logger(__name__)

Classifier = Callable[[str], TargetType]
ResultSink = Callable[["ScanResult"], Awaitable[None]]


@runtime_checkable
class ScanModule(Protocol):
    """Minimal module contract consumed by the engine.

    Replaced by ``modules.base.BaseModule`` in Phase 7 (adds parse/export
    and registry metadata).
    """

    name: str
    target_types: tuple[TargetType, ...]

    def validate(self, target: str) -> bool: ...

    async def run(self, target: str, ctx: ModuleContext) -> Any: ...


@dataclass(slots=True)
class ModuleContext:
    """Everything a module needs while executing."""

    config: Config
    cache: AsyncTTLCache
    logger: Any
    scan_id: str
    target_type: TargetType = TargetType.UNKNOWN
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ModuleRun:
    """Outcome of one module within a scan."""

    module: str
    status: ModuleStatus
    duration: float = 0.0
    result: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "module": self.module,
            "status": self.status.value,
            "duration": round(self.duration, 4),
            "result": self.result,
            "error": self.error,
        }


@dataclass(slots=True)
class ScanResult:
    """Structured outcome of a full scan."""

    scan_id: str
    target: str
    target_type: TargetType
    mode: ScanMode
    status: ScanStatus
    started_at: float
    finished_at: float
    runs: list[ModuleRun] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def duration(self) -> float:
        """Total scan duration in seconds."""
        return self.finished_at - self.started_at

    @property
    def failed_count(self) -> int:
        """Number of modules that failed or timed out."""
        return sum(
            1
            for run in self.runs
            if run.status in (ModuleStatus.FAILED, ModuleStatus.TIMEOUT)
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation (persisted in Phase 3+)."""
        return {
            "scan_id": self.scan_id,
            "target": self.target,
            "target_type": self.target_type.value,
            "mode": self.mode.value,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration": round(self.duration, 4),
            "error": self.error,
            "runs": [run.to_dict() for run in self.runs],
            "findings": self.findings,
        }


def _default_classifier(_target: str) -> TargetType:
    """Placeholder classifier until the input engine lands (Phase 6)."""
    return TargetType.UNKNOWN


class ScanEngine:
    """Orchestrates a scan across the scheduler and worker pool."""

    def __init__(
        self,
        config: Config,
        *,
        cache: AsyncTTLCache | None = None,
        modules: Sequence[ScanModule] | None = None,
        classifier: Classifier | None = None,
        result_sink: ResultSink | None = None,
        concurrency: int | None = None,
        timeout: float | None = None,
    ) -> None:
        self._config = config
        self._cache = cache or AsyncTTLCache(
            max_size=int(config.get("cache.max_size", 1024)),
            default_ttl=float(config.get("cache.ttl", 300.0)),
        )
        self._classifier = classifier or _default_classifier
        self._result_sink = result_sink
        self._concurrency = concurrency or int(config.get("scan.max_workers", 8))
        self._timeout = (
            timeout
            if timeout is not None
            else float(config.get("scan.default_timeout", 30.0))
        )
        self._modules: dict[str, ScanModule] = {}
        for module in modules or ():
            self.register(module)

    @property
    def cache(self) -> AsyncTTLCache:
        """Shared cache exposed to modules."""
        return self._cache

    @property
    def config(self) -> Config:
        """Engine configuration."""
        return self._config

    def register(self, module: ScanModule) -> None:
        """Register a module (last registration wins for a given name)."""
        if not module.name:
            raise ValidationError("module must declare a non-empty name")
        self._modules[module.name] = module

    def module_names(self) -> list[str]:
        """Names of all registered modules."""
        return sorted(self._modules)

    async def scan(
        self,
        target: str,
        *,
        mode: ScanMode | str = ScanMode.QUICK,
        module_names: Sequence[str] | None = None,
    ) -> ScanResult:
        """Run a scan and return its structured result.

        Module failures never fail the scan itself; they are reported per
        run.  Invalid input raises :class:`ValidationError`.
        """
        cleaned = self._validate_target(target)
        scan_mode = ScanMode(mode)
        scan_id = uuid.uuid4().hex[:12]
        target_type = self._classifier(cleaned)
        started = time.time()

        with scan_context(scan_id):
            _log.info(
                "scan %s started for %s (%s)", scan_id, cleaned, target_type.value
            )
            planned, skipped = self._plan(cleaned, target_type, module_names)
            scheduler = TaskScheduler()
            ctx = ModuleContext(
                config=self._config,
                cache=self._cache,
                logger=_log,
                scan_id=scan_id,
                target_type=target_type,
            )
            for module in planned:
                scheduler.submit(
                    module.run(cleaned, ctx),
                    name=module.name,
                    timeout=self._timeout,
                )
            pool = WorkerPool(
                scheduler,
                concurrency=max(self._concurrency, 1),
                default_timeout=self._timeout,
            )
            try:
                await pool.run()
            except Exception as exc:
                _log.error("scan %s aborted: %s", scan_id, exc)
                raise ScanError(f"scan {scan_id} aborted: {exc}") from exc
            result = self._build_result(
                scan_id,
                cleaned,
                target_type,
                scan_mode,
                started,
                planned,
                skipped,
                scheduler,
            )
            _log.info(
                "scan %s finished: %s (%.2fs, %d module(s))",
                scan_id,
                result.status.value,
                result.duration,
                len(result.runs),
            )

        if self._result_sink is not None:
            await self._result_sink(result)
        return result

    async def cancel(self) -> None:
        """Placeholder for GUI-initiated cancellation (wired in Phase 5)."""
        raise NotImplementedError("cancellation lands with the GUI bridge (Phase 5)")

    @staticmethod
    def _validate_target(target: str) -> str:
        if not isinstance(target, str):
            raise ValidationError("target must be a string")
        cleaned = target.strip()
        if not cleaned:
            raise ValidationError("target must not be empty")
        if len(cleaned) > 2048:
            raise ValidationError("target exceeds 2048 characters")
        return cleaned

    def _plan(
        self,
        target: str,
        target_type: TargetType,
        module_names: Sequence[str] | None,
    ) -> tuple[list[ScanModule], list[ModuleRun]]:
        """Select eligible modules; returns (to_run, skipped_runs)."""
        if module_names is not None:
            unknown = [n for n in module_names if n not in self._modules]
            if unknown:
                raise ValidationError(f"unknown module(s): {', '.join(unknown)}")
            candidates = [self._modules[n] for n in module_names]
        else:
            candidates = [self._modules[name] for name in sorted(self._modules)]

        planned: list[ScanModule] = []
        skipped: list[ModuleRun] = []
        for module in candidates:
            if module.target_types and target_type not in module.target_types:
                skipped.append(
                    ModuleRun(
                        module=module.name,
                        status=ModuleStatus.SKIPPED,
                        error=f"not applicable to {target_type.value}",
                    )
                )
                continue
            if not module.validate(target):
                skipped.append(
                    ModuleRun(
                        module=module.name,
                        status=ModuleStatus.SKIPPED,
                        error="target failed module validation",
                    )
                )
                continue
            planned.append(module)
        return planned, skipped

    @staticmethod
    def _build_result(
        scan_id: str,
        target: str,
        target_type: TargetType,
        mode: ScanMode,
        started: float,
        planned: list[ScanModule],
        skipped: list[ModuleRun],
        scheduler: TaskScheduler,
    ) -> ScanResult:
        runs: list[ModuleRun] = list(skipped)
        findings: list[dict[str, Any]] = []
        tasks = {task.name: task for task in scheduler.tasks}
        for module in planned:
            task = tasks.get(module.name)
            if task is None:
                runs.append(
                    ModuleRun(
                        module=module.name,
                        status=ModuleStatus.FAILED,
                        error="missing task",
                    )
                )
                continue
            duration = task.duration or 0.0
            if task.state is TaskState.DONE:
                runs.append(
                    ModuleRun(
                        module=module.name,
                        status=ModuleStatus.SUCCESS,
                        duration=duration,
                        result=task.result,
                    )
                )
                if task.result is not None:
                    findings.append({"module": module.name, "data": task.result})
            elif task.state is TaskState.CANCELLED:
                runs.append(
                    ModuleRun(
                        module=module.name,
                        status=ModuleStatus.CANCELLED,
                        duration=duration,
                    )
                )
            elif isinstance(task.error, TaskTimeoutError):
                runs.append(
                    ModuleRun(
                        module=module.name,
                        status=ModuleStatus.TIMEOUT,
                        duration=duration,
                        error=str(task.error),
                    )
                )
            else:
                runs.append(
                    ModuleRun(
                        module=module.name,
                        status=ModuleStatus.FAILED,
                        duration=duration,
                        error=str(task.error) if task.error else "unknown error",
                    )
                )
        runs.sort(key=lambda r: r.module)
        return ScanResult(
            scan_id=scan_id,
            target=target,
            target_type=target_type,
            mode=mode,
            status=ScanStatus.COMPLETED,
            started_at=started,
            finished_at=time.time(),
            runs=runs,
            findings=findings,
        )
