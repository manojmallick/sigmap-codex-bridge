"""Reproducible paired raw-versus-SigMap benchmark execution."""

from __future__ import annotations

import json
import os
import platform
import re
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from . import __version__
from .benchmark import BenchmarkTask
from .codex import CodexResult, CodexRunner, CodexStatus
from .git import FileChange, GitError, GitRepository
from .preflight import PreflightResult, preflight_task
from .process import ProcessResult, run_process
from .scoring import BenchmarkObservation, BenchmarkScore, score_observation
from .sigmap import ContextResult, ContextStatus, SigMapContextProvider
from .worktree import WorktreeError, WorktreeLease, WorktreeManager


ARTIFACT_SCHEMA_VERSION = 1
CONDITIONS = ("raw", "sigmap")


class BenchmarkRunError(RuntimeError):
    """Raised when an experiment cannot safely begin."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _safe_label(value: str) -> str:
    label = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")
    return label[:64] or "task"


def condition_order(repetition: int, start_condition: str = "raw") -> tuple[str, str]:
    """Return a deterministic alternating order for one-based repetitions."""

    if repetition < 1:
        raise ValueError("repetition must be positive")
    if start_condition not in CONDITIONS:
        raise ValueError(f"start_condition must be one of: {', '.join(CONDITIONS)}")
    other = "sigmap" if start_condition == "raw" else "raw"
    return (start_condition, other) if repetition % 2 else (other, start_condition)


def _process_dict(result: ProcessResult | None) -> dict[str, object] | None:
    return result.to_dict() if result is not None else None


def _patch_lines(worktree: Path, changes: Sequence[FileChange]) -> tuple[int, int]:
    result = run_process(
        ("git", "-C", str(worktree), "diff", "--numstat", "HEAD"),
        cwd=worktree,
        timeout_seconds=30,
    )
    if not result.ok:
        raise GitError(result.stderr.strip() or "git diff --numstat failed")

    additions = 0
    deletions = 0
    counted: set[str] = set()
    for line in result.stdout.splitlines():
        fields = line.split("\t", 2)
        if len(fields) != 3:
            continue
        added, deleted, path = fields
        counted.add(path)
        if added.isdigit():
            additions += int(added)
        if deleted.isdigit():
            deletions += int(deleted)

    for change in changes:
        if change.status != "added" or change.path in counted:
            continue
        path = worktree / change.path
        try:
            additions += len(path.read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeError):
            pass
    return additions, deletions


@dataclass(frozen=True)
class RunEnvironment:
    bridge_version: str
    python_version: str
    platform: str
    model: str | None
    sandbox: str
    codex_command: tuple[str, ...]
    sigmap_command: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["codex_command"] = list(self.codex_command)
        value["sigmap_command"] = list(self.sigmap_command)
        return value


@dataclass(frozen=True)
class BenchmarkRunArtifact:
    experiment_id: str
    task_id: str
    task_file: str
    resolved_revision: str
    repetition: int
    pair_id: str
    condition: str
    condition_order: tuple[str, str]
    order_position: int
    started_at: str
    finished_at: str
    exact_command: tuple[str, ...]
    environment: RunEnvironment
    setup: ProcessResult | None
    context: ContextResult
    codex: CodexResult | None
    test: ProcessResult | None
    static_checks: tuple[ProcessResult, ...]
    changes: tuple[FileChange, ...]
    score: BenchmarkScore
    worktree_cleaned: bool
    failure_details: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
            "experiment_id": self.experiment_id,
            "task_id": self.task_id,
            "task_file": self.task_file,
            "resolved_revision": self.resolved_revision,
            "repetition": self.repetition,
            "pair_id": self.pair_id,
            "condition": self.condition,
            "condition_order": list(self.condition_order),
            "order_position": self.order_position,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exact_command": list(self.exact_command),
            "environment": self.environment.to_dict(),
            "bridge": {
                "requested_context": self.condition,
                "context": self.context.to_dict(),
                "codex": self.codex.to_dict() if self.codex else None,
                "setup": _process_dict(self.setup),
                "test": _process_dict(self.test),
                "static_checks": [result.to_dict() for result in self.static_checks],
                "changes": [change.to_dict() for change in self.changes],
                "worktree_cleaned": self.worktree_cleaned,
            },
            "score": self.score.to_dict(),
            "failure_details": list(self.failure_details),
        }


CodexRunnerFactory = Callable[[float], CodexRunner]


class PairedBenchmarkRunner:
    """Execute complete paired conditions and retain every attempted run."""

    def __init__(
        self,
        *,
        context_provider: SigMapContextProvider | None = None,
        codex_runner_factory: CodexRunnerFactory | None = None,
    ) -> None:
        self.context_provider = context_provider or SigMapContextProvider()
        self.codex_runner_factory = codex_runner_factory or (
            lambda timeout: CodexRunner(timeout_seconds=timeout)
        )

    def environment(
        self,
        *,
        model: str | None,
        sandbox: str,
        codex_command: Sequence[str] | None = None,
    ) -> RunEnvironment:
        codex = (
            CodexRunner(command=codex_command)
            if codex_command is not None
            else self.codex_runner_factory(1.0)
        )
        return RunEnvironment(
            bridge_version=__version__,
            python_version=platform.python_version(),
            platform=f"{platform.system()} {platform.release()} ({platform.machine()})",
            model=model,
            sandbox=sandbox,
            codex_command=codex.command,
            sigmap_command=self.context_provider.command,
        )

    def run_task(
        self,
        task: BenchmarkTask,
        *,
        task_file: str | Path,
        output_dir: str | Path,
        experiment_id: str,
        sandbox: str = "workspace-write",
        model: str | None = None,
        codex_command: Sequence[str] | None = None,
        start_condition: str = "raw",
        context_timeout_seconds: float = 120.0,
        worktree_root: str | Path | None = None,
        exact_command: Sequence[str] = (),
    ) -> tuple[BenchmarkRunArtifact, ...]:
        if context_timeout_seconds <= 0:
            raise BenchmarkRunError("context timeout must be greater than zero")
        preflight = preflight_task(task, worktree_root=worktree_root)
        self._require_preflight(preflight)
        assert preflight.revision is not None

        artifacts: list[BenchmarkRunArtifact] = []
        task_path = Path(task_file).resolve()
        task_id = _safe_label(task_path.stem)
        destination = Path(output_dir).resolve()
        environment = self.environment(
            model=model,
            sandbox=sandbox,
            codex_command=codex_command,
        )
        for repetition in range(1, task.repetitions + 1):
            order = condition_order(repetition, start_condition)
            pair_id = f"{task_id}-r{repetition:03d}"
            for position, condition in enumerate(order, start=1):
                artifact = self._run_one(
                    task,
                    task_id=task_id,
                    task_file=task_path,
                    experiment_id=experiment_id,
                    resolved_revision=preflight.revision,
                    repetition=repetition,
                    pair_id=pair_id,
                    condition=condition,
                    order=order,
                    position=position,
                    sandbox=sandbox,
                    model=model,
                    codex_command=tuple(codex_command) if codex_command else None,
                    context_timeout_seconds=context_timeout_seconds,
                    worktree_root=worktree_root,
                    exact_command=tuple(exact_command),
                    environment=environment,
                )
                filename = f"{pair_id}-{position}-{condition}.json"
                _atomic_json(destination / filename, artifact.to_dict())
                artifacts.append(artifact)
        return tuple(artifacts)

    @staticmethod
    def _require_preflight(preflight: PreflightResult) -> None:
        if preflight.valid:
            return
        failed = [check.detail for check in preflight.checks if not check.passed]
        raise BenchmarkRunError("benchmark preflight failed: " + "; ".join(failed))

    def _run_one(
        self,
        task: BenchmarkTask,
        *,
        task_id: str,
        task_file: Path,
        experiment_id: str,
        resolved_revision: str,
        repetition: int,
        pair_id: str,
        condition: str,
        order: tuple[str, str],
        position: int,
        sandbox: str,
        model: str | None,
        codex_command: tuple[str, ...] | None,
        context_timeout_seconds: float,
        worktree_root: str | Path | None,
        exact_command: tuple[str, ...],
        environment: RunEnvironment,
    ) -> BenchmarkRunArtifact:
        started_at = _utc_now()
        manager = WorktreeManager(task.repository, root=worktree_root)
        lease: WorktreeLease | None = None
        setup: ProcessResult | None = None
        context = ContextResult.disabled()
        codex: CodexResult | None = None
        test: ProcessResult | None = None
        static_checks: tuple[ProcessResult, ...] = ()
        changes: tuple[FileChange, ...] = ()
        lines_added = 0
        lines_deleted = 0
        cleaned = False
        failures: list[str] = []

        try:
            lease = manager.create(f"benchmark-{uuid.uuid4().hex}", resolved_revision)
            worktree = Path(lease.path)
            if task.setup_command is not None:
                setup = run_process(
                    task.setup_command,
                    cwd=worktree,
                    timeout_seconds=task.timeout_seconds,
                )
                if not setup.ok:
                    failures.append("setup command failed")
                elif GitRepository(worktree).changes():
                    failures.append("setup left Git-visible changes")

            setup_ready = setup is None or (
                setup.ok and "setup left Git-visible changes" not in failures
            )
            if setup_ready:
                if condition == "sigmap":
                    provider = SigMapContextProvider(
                        command=self.context_provider.command,
                        top=self.context_provider.top,
                        timeout_seconds=context_timeout_seconds,
                        env=self.context_provider.env,
                    )
                    context = provider.retrieve(task.prompt, worktree)
                    if context.status is not ContextStatus.READY:
                        failures.append(
                            f"SigMap context unavailable: {context.status.value}"
                        )
                if condition == "raw" or context.status is ContextStatus.READY:
                    runner = (
                        CodexRunner(
                            command=codex_command,
                            timeout_seconds=task.timeout_seconds,
                        )
                        if codex_command is not None
                        else self.codex_runner_factory(task.timeout_seconds)
                    )
                    codex = runner.run(
                        task.prompt,
                        worktree,
                        context=context.context if condition == "sigmap" else None,
                        sandbox=sandbox,
                        model=model,
                    )
                    if codex.status is not CodexStatus.SUCCEEDED:
                        failures.append(f"Codex failed: {codex.status.value}")

                test = run_process(
                    task.test_command,
                    cwd=worktree,
                    timeout_seconds=task.timeout_seconds,
                )
                if not test.ok:
                    failures.append("candidate tests failed")
                static_checks = tuple(
                    run_process(
                        command,
                        cwd=worktree,
                        timeout_seconds=task.timeout_seconds,
                    )
                    for command in task.static_check_commands
                )
                if any(not result.ok for result in static_checks):
                    failures.append("candidate static checks failed")

            changes = GitRepository(worktree).changes()
            lines_added, lines_deleted = _patch_lines(worktree, changes)
        except (GitError, WorktreeError, OSError) as error:
            failures.append(str(error))
        finally:
            if lease is not None:
                try:
                    manager.cleanup(lease)
                    cleaned = True
                except (GitError, WorktreeError, OSError) as error:
                    failures.append(f"worktree cleanup failed: {error}")

        codex_succeeded = codex is not None and codex.status is CodexStatus.SUCCEEDED
        static_results = (
            tuple(result.ok for result in static_checks)
            if len(static_checks) == len(task.static_check_commands)
            else tuple(False for _command in task.static_check_commands)
        )
        observation = BenchmarkObservation(
            test_passed=bool(codex_succeeded and test is not None and test.ok),
            static_check_results=static_results,
            changed_files=tuple(change.path for change in changes),
            touched_symbols=(),
            lines_added=lines_added,
            lines_deleted=lines_deleted,
            runtime_seconds=(codex.process.duration_seconds if codex else 0.0),
            input_tokens=codex.usage.input_tokens if codex else 0,
            cached_input_tokens=codex.usage.cached_input_tokens if codex else 0,
            output_tokens=codex.usage.output_tokens if codex else 0,
            tool_events=codex.tool_event_count if codex else 0,
            command_events=codex.command_event_count if codex else 0,
        )
        score = score_observation(task, observation)
        return BenchmarkRunArtifact(
            experiment_id=experiment_id,
            task_id=task_id,
            task_file=str(task_file),
            resolved_revision=resolved_revision,
            repetition=repetition,
            pair_id=pair_id,
            condition=condition,
            condition_order=order,
            order_position=position,
            started_at=started_at,
            finished_at=_utc_now(),
            exact_command=exact_command,
            environment=environment,
            setup=setup,
            context=context,
            codex=codex,
            test=test,
            static_checks=static_checks,
            changes=changes,
            score=score,
            worktree_cleaned=cleaned,
            failure_details=tuple(failures),
        )


def default_exact_command(argv: Sequence[str]) -> tuple[str, ...]:
    return (sys.executable, "-m", "sigmap_codex_bridge", *tuple(argv))
