"""Atomic, resumable, pair-aware benchmark execution."""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping, Sequence

from .benchmark import BenchmarkTask
from .experiment import (
    BenchmarkRunArtifact,
    PairedBenchmarkRunner,
    PreparedBenchmarkTask,
    condition_order,
)
from .worktree import WorktreeError, WorktreeManager


EXECUTION_STATE_SCHEMA_VERSION = 1
STATE_FIELDS = {
    "execution_state_schema_version",
    "execution_id",
    "experiment_id",
    "configuration_digest",
    "status",
    "stop_reason",
    "max_workers",
    "budgets",
    "usage",
    "output_dir",
    "worktree_root",
    "settings",
    "tasks",
    "pairs",
    "transition_count",
}
PAIR_STATUSES = {"pending", "partial", "running", "complete"}
ATTEMPT_STATUSES = {"pending", "running", "complete"}
EXECUTION_STATUSES = {"ready", "running", "stopped", "completed"}


class ExecutionError(ValueError):
    """Raised when resumable execution cannot proceed safely."""


@dataclass(frozen=True)
class ExecutionBudget:
    max_pairs: int | None = None
    max_runtime_seconds: float | None = None
    max_total_tokens: int | None = None

    def validate(self) -> None:
        if (
            self.max_pairs is not None
            and (
                not isinstance(self.max_pairs, int)
                or isinstance(self.max_pairs, bool)
                or self.max_pairs < 1
            )
        ):
            raise ExecutionError("max_pairs must be a positive integer")
        if (
            self.max_runtime_seconds is not None
            and (
                isinstance(self.max_runtime_seconds, bool)
                or not isinstance(self.max_runtime_seconds, (int, float))
                or not math.isfinite(float(self.max_runtime_seconds))
                or self.max_runtime_seconds <= 0
            )
        ):
            raise ExecutionError("max_runtime_seconds must be a finite number > 0")
        if (
            self.max_total_tokens is not None
            and (
                not isinstance(self.max_total_tokens, int)
                or isinstance(self.max_total_tokens, bool)
                or self.max_total_tokens < 1
            )
        ):
            raise ExecutionError("max_total_tokens must be a positive integer")

    def to_dict(self) -> dict[str, object]:
        return {
            "max_pairs": self.max_pairs,
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_total_tokens": self.max_total_tokens,
        }


@dataclass(frozen=True)
class ExecutionTask:
    task_file: str | Path
    task: BenchmarkTask
    benchmark_pack: Mapping[str, object] | None = None


TransitionHook = Callable[[str, Mapping[str, object]], None]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _atomic_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise ExecutionError(f"cannot write execution state: {error}") from error


def _strict(value: object, field: str, expected: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ExecutionError(f"{field} must be an object")
    fields = set(value)
    missing = sorted(expected - fields)
    unknown = sorted(fields - expected)
    if missing:
        raise ExecutionError(f"{field} missing fields: {', '.join(missing)}")
    if unknown:
        raise ExecutionError(f"{field} unknown fields: {', '.join(unknown)}")
    return value


def _safe_artifact_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ExecutionError("attempt artifact_path must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or len(path.parts) != 1 or path.name != value:
        raise ExecutionError("attempt artifact_path must be a safe output filename")
    return value


def _non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ExecutionError(f"{field} must be a non-empty string")
    return value


def _sha256_string(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ExecutionError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _nonnegative_integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ExecutionError(f"{field} must be a non-negative integer")
    return value


def _positive_finite_number(value: object, field: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise ExecutionError(f"{field} must be a finite number > 0")
    return float(value)


def load_execution_state(path: str | Path) -> dict[str, object]:
    """Load a strict state snapshot without trusting its artifact references."""

    state_path = Path(path).resolve()
    try:
        value = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExecutionError(f"cannot read execution state: {error}") from error
    state = dict(_strict(value, "state", STATE_FIELDS))
    version = state["execution_state_schema_version"]
    if version != EXECUTION_STATE_SCHEMA_VERSION or isinstance(version, bool):
        raise ExecutionError("unsupported execution state schema")
    for field in ("execution_id", "experiment_id"):
        _non_empty_string(state[field], f"state {field}")
    _sha256_string(state["configuration_digest"], "state configuration_digest")
    if state["status"] not in EXECUTION_STATUSES:
        raise ExecutionError("state status is invalid")
    stop_reason = state["stop_reason"]
    if stop_reason is not None:
        reason = _strict(
            stop_reason,
            "state stop_reason",
            {
                "kind",
                "budget",
                "threshold",
                "observed",
                "overshoot",
                "in_flight_pairs",
                "monetary_cost",
            },
        )
        _non_empty_string(reason["kind"], "state stop_reason kind")
        if reason["budget"] not in {
            None,
            "max_pairs",
            "max_runtime_seconds",
            "max_total_tokens",
        }:
            raise ExecutionError("state stop_reason budget is invalid")
        for field in ("threshold", "observed", "overshoot"):
            number = reason[field]
            if (
                number is not None
                and (
                    not isinstance(number, (int, float))
                    or isinstance(number, bool)
                    or not math.isfinite(float(number))
                    or number < 0
                )
            ):
                raise ExecutionError(
                    f"state stop_reason {field} must be a finite non-negative number"
                )
        if reason["overshoot"] is None:
            raise ExecutionError("state stop_reason overshoot cannot be null")
        _nonnegative_integer(
            reason["in_flight_pairs"], "state stop_reason in_flight_pairs"
        )
        if reason["monetary_cost"] is not None:
            raise ExecutionError("state stop_reason monetary_cost must be null")
    if state["status"] == "stopped" and stop_reason is None:
        raise ExecutionError("state stopped status requires a stop_reason")
    if state["status"] != "stopped" and stop_reason is not None:
        raise ExecutionError("state stop_reason is only valid when stopped")
    _nonnegative_integer(state["transition_count"], "state transition_count")
    if (
        not isinstance(state["max_workers"], int)
        or isinstance(state["max_workers"], bool)
        or not 1 <= state["max_workers"] <= 32
    ):
        raise ExecutionError("state max_workers must be between 1 and 32")
    budgets = _strict(
        state["budgets"],
        "state budgets",
        {"max_pairs", "max_runtime_seconds", "max_total_tokens"},
    )
    ExecutionBudget(
        max_pairs=budgets["max_pairs"],  # type: ignore[arg-type]
        max_runtime_seconds=budgets["max_runtime_seconds"],  # type: ignore[arg-type]
        max_total_tokens=budgets["max_total_tokens"],  # type: ignore[arg-type]
    ).validate()
    usage = _strict(
        state["usage"],
        "state usage",
        {"completed_pairs", "completed_attempts", "runtime_seconds", "total_tokens"},
    )
    _nonnegative_integer(usage["completed_pairs"], "state completed_pairs")
    _nonnegative_integer(usage["completed_attempts"], "state completed_attempts")
    _nonnegative_integer(usage["total_tokens"], "state total_tokens")
    runtime = usage["runtime_seconds"]
    if (
        not isinstance(runtime, (int, float))
        or isinstance(runtime, bool)
        or not math.isfinite(float(runtime))
        or runtime < 0
    ):
        raise ExecutionError("state runtime_seconds must be a finite number >= 0")
    settings = _strict(
        state["settings"],
        "state settings",
        {
            "sandbox",
            "model",
            "codex_command",
            "context_timeout_seconds",
            "start_condition",
            "exact_command",
        },
    )
    if settings["sandbox"] not in {
        "read-only",
        "workspace-write",
        "danger-full-access",
    }:
        raise ExecutionError("state sandbox is invalid")
    if settings["model"] is not None:
        _non_empty_string(settings["model"], "state model")
    for field in ("codex_command", "exact_command"):
        command = settings[field]
        if command is None and field == "codex_command":
            continue
        if (
            not isinstance(command, list)
            or not command
            or any(not isinstance(value, str) or not value for value in command)
        ):
            raise ExecutionError(f"state {field} must be a non-empty argument array")
    _positive_finite_number(
        settings["context_timeout_seconds"], "state context_timeout_seconds"
    )
    if settings["start_condition"] not in {"raw", "sigmap"}:
        raise ExecutionError("state start_condition is invalid")
    _non_empty_string(state["output_dir"], "state output_dir")
    if state["worktree_root"] is not None:
        _non_empty_string(state["worktree_root"], "state worktree_root")
    tasks = state["tasks"]
    pairs = state["pairs"]
    if not isinstance(tasks, list) or not tasks:
        raise ExecutionError("state tasks must be a non-empty array")
    if not isinstance(pairs, list) or not pairs:
        raise ExecutionError("state pairs must be a non-empty array")
    task_ids: set[str] = set()
    for index, task_value in enumerate(tasks):
        task = _strict(
            task_value,
            f"state tasks[{index}]",
            {
                "task_file",
                "task_sha256",
                "repository",
                "resolved_revision",
                "task_id",
                "repetitions",
                "benchmark_pack",
            },
        )
        for field in ("task_file", "repository", "resolved_revision", "task_id"):
            _non_empty_string(task[field], f"state task {index} {field}")
        _sha256_string(task["task_sha256"], f"state task {index} task_sha256")
        task_id = str(task["task_id"])
        if task_id in task_ids:
            raise ExecutionError("state task identities must be unique")
        task_ids.add(task_id)
        repetitions = task["repetitions"]
        if (
            not isinstance(repetitions, int)
            or isinstance(repetitions, bool)
            or repetitions < 1
        ):
            raise ExecutionError("state task repetitions must be a positive integer")
        if task["benchmark_pack"] is not None and not isinstance(
            task["benchmark_pack"], Mapping
        ):
            raise ExecutionError("state task benchmark_pack must be an object or null")
    pair_keys: set[str] = set()
    pair_coordinates: set[tuple[int, int]] = set()
    attempt_ids: set[str] = set()
    run_ids: set[str] = set()
    artifact_paths: set[str] = set()
    for index, pair_value in enumerate(pairs):
        pair = _strict(
            pair_value,
            f"state pairs[{index}]",
            {
                "pair_key",
                "task_index",
                "repetition",
                "pair_id",
                "order",
                "status",
                "attempts",
            },
        )
        pair_key = pair["pair_key"]
        if not isinstance(pair_key, str) or not pair_key or pair_key in pair_keys:
            raise ExecutionError("state pair identities must be non-empty and unique")
        pair_keys.add(pair_key)
        task_index = pair["task_index"]
        if (
            not isinstance(task_index, int)
            or isinstance(task_index, bool)
            or not 0 <= task_index < len(tasks)
        ):
            raise ExecutionError(f"state pair {pair_key} has invalid task_index")
        repetition = pair["repetition"]
        task_repetitions = tasks[task_index]["repetitions"]
        if (
            not isinstance(repetition, int)
            or isinstance(repetition, bool)
            or not 1 <= repetition <= task_repetitions
        ):
            raise ExecutionError(f"state pair {pair_key} has invalid repetition")
        coordinate = (task_index, repetition)
        if coordinate in pair_coordinates:
            raise ExecutionError("state task/repetition pair identities must be unique")
        pair_coordinates.add(coordinate)
        _non_empty_string(pair["pair_id"], f"state pair {pair_key} pair_id")
        order = pair["order"]
        if (
            not isinstance(order, list)
            or len(order) != 2
            or set(order) != {"raw", "sigmap"}
        ):
            raise ExecutionError(f"state pair {pair_key} has invalid order")
        if pair["status"] not in PAIR_STATUSES:
            raise ExecutionError(f"state pair {pair_key} has invalid status")
        attempts = pair["attempts"]
        if not isinstance(attempts, list) or len(attempts) != 2:
            raise ExecutionError(f"state pair {pair_key} must contain two attempts")
        conditions: set[str] = set()
        for attempt_index, attempt_value in enumerate(attempts):
            attempt = _strict(
                attempt_value,
                f"state pair {pair_key} attempts[{attempt_index}]",
                {
                    "attempt_id",
                    "condition",
                    "position",
                    "status",
                    "artifact_path",
                    "artifact_sha256",
                    "run_id",
                },
            )
            attempt_id = attempt["attempt_id"]
            condition = attempt["condition"]
            if (
                not isinstance(attempt_id, str)
                or not attempt_id
                or attempt_id in attempt_ids
            ):
                raise ExecutionError("state attempt identities must be non-empty and unique")
            attempt_ids.add(attempt_id)
            if condition not in {"raw", "sigmap"} or condition in conditions:
                raise ExecutionError(f"state pair {pair_key} has invalid conditions")
            conditions.add(str(condition))
            if attempt["status"] not in ATTEMPT_STATUSES:
                raise ExecutionError(f"state attempt {attempt_id} has invalid status")
            if attempt["position"] != attempt_index + 1:
                raise ExecutionError(f"state attempt {attempt_id} has invalid position")
            if order[attempt_index] != condition:
                raise ExecutionError(f"state pair {pair_key} attempt order differs")
            artifact_path = _safe_artifact_path(attempt["artifact_path"])
            if artifact_path in artifact_paths:
                raise ExecutionError("state artifact paths must be unique")
            artifact_paths.add(artifact_path)
            digest = attempt["artifact_sha256"]
            if digest is not None and (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise ExecutionError(f"state attempt {attempt_id} has invalid SHA-256")
            if attempt["status"] == "complete" and digest is None:
                raise ExecutionError(
                    f"state complete attempt {attempt_id} must have an artifact digest"
                )
            if attempt["status"] != "complete" and digest is not None:
                raise ExecutionError(
                    f"state incomplete attempt {attempt_id} cannot have an artifact digest"
                )
            run_id = _non_empty_string(
                attempt["run_id"], f"state attempt {attempt_id} run_id"
            )
            if run_id in run_ids:
                raise ExecutionError("state attempt run IDs must be unique")
            run_ids.add(run_id)
        completed = sum(attempt["status"] == "complete" for attempt in attempts)
        if pair["status"] == "complete" and completed != 2:
            raise ExecutionError(f"state complete pair {pair_key} is inconsistent")
        if pair["status"] == "partial" and completed != 1:
            raise ExecutionError(f"state partial pair {pair_key} is inconsistent")
        if pair["status"] == "pending" and completed != 0:
            raise ExecutionError(f"state pending pair {pair_key} is inconsistent")
    expected_coordinates = {
        (task_index, repetition)
        for task_index, task in enumerate(tasks)
        for repetition in range(1, int(task["repetitions"]) + 1)
    }
    if pair_coordinates != expected_coordinates:
        raise ExecutionError("state pairs do not cover every declared task repetition")
    if int(usage["completed_pairs"]) > len(pairs):
        raise ExecutionError("state completed_pairs exceeds declared pairs")
    if int(usage["completed_attempts"]) > len(pairs) * 2:
        raise ExecutionError("state completed_attempts exceeds declared attempts")
    return state


def _artifact_usage(artifact: Mapping[str, object]) -> tuple[float, int]:
    score = artifact.get("score")
    if not isinstance(score, Mapping):
        return 0.0, 0
    runtime = score.get("runtime_seconds")
    input_tokens = score.get("input_tokens")
    output_tokens = score.get("output_tokens")
    runtime_value = (
        float(runtime)
        if isinstance(runtime, (int, float))
        and not isinstance(runtime, bool)
        and math.isfinite(float(runtime))
        and runtime >= 0
        else 0.0
    )
    token_values = [
        value
        for value in (input_tokens, output_tokens)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    ]
    return runtime_value, sum(token_values)


class ResumableBenchmarkExecutor:
    """Execute complete pairs with atomic checkpoints and bounded concurrency."""

    def __init__(
        self,
        runner: PairedBenchmarkRunner,
        *,
        transition_hook: TransitionHook | None = None,
    ) -> None:
        self.runner = runner
        self.transition_hook = transition_hook
        self._lock = threading.RLock()

    def execute(
        self,
        tasks: Sequence[ExecutionTask],
        *,
        state_file: str | Path,
        output_dir: str | Path,
        experiment_id: str,
        sandbox: str,
        model: str | None,
        codex_command: Sequence[str] | None,
        start_condition: str,
        context_timeout_seconds: float,
        worktree_root: str | Path | None,
        exact_command: Sequence[str],
        max_workers: int,
        budget: ExecutionBudget,
        resume: bool,
    ) -> dict[str, object]:
        if not tasks:
            raise ExecutionError("at least one execution task is required")
        if not 1 <= max_workers <= 32:
            raise ExecutionError("max_workers must be between 1 and 32")
        if start_condition not in {"raw", "sigmap"}:
            raise ExecutionError("start_condition must be raw or sigmap")
        budget.validate()
        state_path = Path(state_file).resolve()
        destination = Path(output_dir).resolve()
        worktrees = Path(worktree_root).resolve() if worktree_root else None
        prepared = tuple(
            self.runner.prepare_task(
                item.task,
                task_file=item.task_file,
                sandbox=sandbox,
                model=model,
                codex_command=codex_command,
                context_timeout_seconds=context_timeout_seconds,
                worktree_root=worktrees,
            )
            for item in tasks
        )
        task_ids = [item.task_id for item in prepared]
        if len(task_ids) != len(set(task_ids)):
            raise ExecutionError("execution task files must produce unique task IDs")
        configuration = self._configuration(
            tasks,
            prepared,
            output_dir=destination,
            worktree_root=worktrees,
            experiment_id=experiment_id,
            sandbox=sandbox,
            model=model,
            codex_command=codex_command,
            start_condition=start_condition,
            context_timeout_seconds=context_timeout_seconds,
            exact_command=exact_command,
        )
        digest_configuration = json.loads(json.dumps(configuration))
        digest_configuration["settings"].pop("exact_command")
        digest = _sha256(_canonical(digest_configuration))
        if state_path.exists():
            if not resume:
                raise ExecutionError("execution state exists; pass --resume to continue")
            state = load_execution_state(state_path)
            if state["configuration_digest"] != digest:
                raise ExecutionError("execution configuration differs from persisted state")
            if (
                state["experiment_id"] != experiment_id
                or state["output_dir"] != str(destination)
                or state["worktree_root"]
                != (str(worktrees) if worktrees else None)
                or state["tasks"] != configuration["tasks"]
            ):
                raise ExecutionError("execution state paths or tasks differ from configuration")
            persisted_settings = dict(state["settings"])
            current_settings = dict(configuration["settings"])
            persisted_settings.pop("exact_command")
            current_settings.pop("exact_command")
            if persisted_settings != current_settings:
                raise ExecutionError("execution settings differ from persisted state")
            state["max_workers"] = max_workers
            state["budgets"] = budget.to_dict()
            self._reconcile(state, state_path, prepared, tasks, destination, worktrees)
        else:
            if resume:
                raise ExecutionError("cannot resume because execution state does not exist")
            if destination.exists() and any(destination.iterdir()):
                raise ExecutionError("resumable output directory must be absent or empty")
            destination.mkdir(parents=True, exist_ok=True)
            state = self._initial_state(
                configuration,
                digest=digest,
                experiment_id=experiment_id,
                output_dir=destination,
                worktree_root=worktrees,
                max_workers=max_workers,
                budget=budget,
                start_condition=start_condition,
                tasks=tasks,
                prepared=prepared,
            )
            _atomic_json(state_path, state)
            self._hook("state_created", state)

        state["status"] = "running"
        state["stop_reason"] = None
        self._transition(state_path, state, "execution_started")
        self._run_pairs(
            state,
            state_path,
            prepared,
            tasks,
            destination,
            worktrees,
            max_workers=max_workers,
            budget=budget,
        )
        return state

    def _configuration(
        self,
        tasks: Sequence[ExecutionTask],
        prepared: Sequence[PreparedBenchmarkTask],
        *,
        output_dir: Path,
        worktree_root: Path | None,
        experiment_id: str,
        sandbox: str,
        model: str | None,
        codex_command: Sequence[str] | None,
        start_condition: str,
        context_timeout_seconds: float,
        exact_command: Sequence[str],
    ) -> dict[str, object]:
        task_values = []
        for item, ready in zip(tasks, prepared, strict=True):
            task_path = Path(item.task_file).resolve()
            try:
                task_hash = _sha256(task_path.read_bytes())
            except OSError as error:
                raise ExecutionError(f"cannot hash task file: {error}") from error
            task_values.append(
                {
                    "task_file": str(task_path),
                    "task_sha256": task_hash,
                    "repository": item.task.repository,
                    "resolved_revision": ready.resolved_revision,
                    "task_id": ready.task_id,
                    "repetitions": item.task.repetitions,
                    "benchmark_pack": (
                        dict(item.benchmark_pack) if item.benchmark_pack else None
                    ),
                }
            )
        return {
            "experiment_id": experiment_id,
            "output_dir": str(output_dir),
            "worktree_root": str(worktree_root) if worktree_root else None,
            "settings": {
                "sandbox": sandbox,
                "model": model,
                "codex_command": list(codex_command) if codex_command else None,
                "context_timeout_seconds": context_timeout_seconds,
                "start_condition": start_condition,
                "exact_command": list(exact_command),
            },
            "tasks": task_values,
        }

    def _initial_state(
        self,
        configuration: Mapping[str, object],
        *,
        digest: str,
        experiment_id: str,
        output_dir: Path,
        worktree_root: Path | None,
        max_workers: int,
        budget: ExecutionBudget,
        start_condition: str,
        tasks: Sequence[ExecutionTask],
        prepared: Sequence[PreparedBenchmarkTask],
    ) -> dict[str, object]:
        execution_id = digest[:16]
        pairs = []
        for task_index, (item, ready) in enumerate(
            zip(tasks, prepared, strict=True)
        ):
            for repetition in range(1, item.task.repetitions + 1):
                order = condition_order(repetition, start_condition)
                pair_id = f"{ready.task_id}-r{repetition:03d}"
                attempts = []
                for position, condition in enumerate(order, start=1):
                    attempt_id = f"{pair_id}:{condition}"
                    attempts.append(
                        {
                            "attempt_id": attempt_id,
                            "condition": condition,
                            "position": position,
                            "status": "pending",
                            "artifact_path": f"{pair_id}-{position}-{condition}.json",
                            "artifact_sha256": None,
                            "run_id": (
                                f"benchmark-{execution_id}-{ready.task_id}-"
                                f"r{repetition:03d}-{condition}"
                            ),
                        }
                    )
                pairs.append(
                    {
                        "pair_key": f"{ready.task_id}:r{repetition:03d}",
                        "task_index": task_index,
                        "repetition": repetition,
                        "pair_id": pair_id,
                        "order": list(order),
                        "status": "pending",
                        "attempts": attempts,
                    }
                )
        return {
            "execution_state_schema_version": EXECUTION_STATE_SCHEMA_VERSION,
            "execution_id": execution_id,
            "experiment_id": experiment_id,
            "configuration_digest": digest,
            "status": "ready",
            "stop_reason": None,
            "max_workers": max_workers,
            "budgets": budget.to_dict(),
            "usage": self._empty_usage(),
            "output_dir": str(output_dir),
            "worktree_root": str(worktree_root) if worktree_root else None,
            "settings": configuration["settings"],
            "tasks": configuration["tasks"],
            "pairs": pairs,
            "transition_count": 0,
        }

    @staticmethod
    def _empty_usage() -> dict[str, object]:
        return {
            "completed_pairs": 0,
            "completed_attempts": 0,
            "runtime_seconds": 0.0,
            "total_tokens": 0,
        }

    def _hook(self, transition: str, state: Mapping[str, object]) -> None:
        if self.transition_hook is not None:
            self.transition_hook(transition, state)

    def _transition(
        self, state_path: Path, state: dict[str, object], transition: str
    ) -> None:
        with self._lock:
            state["transition_count"] = int(state["transition_count"]) + 1
            _atomic_json(state_path, state)
            self._hook(transition, state)

    def _artifact(
        self,
        path: Path,
        *,
        state: Mapping[str, object],
        pair: Mapping[str, object],
        attempt: Mapping[str, object],
        prepared: PreparedBenchmarkTask,
        benchmark_pack: Mapping[str, object] | None,
    ) -> dict[str, object]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ExecutionError(f"cannot read retained artifact {path}: {error}") from error
        if not isinstance(value, dict) or value.get("artifact_schema_version") != 1:
            raise ExecutionError(f"retained artifact has unsupported schema: {path}")
        expected = {
            "experiment_id": state["experiment_id"],
            "task_id": prepared.task_id,
            "resolved_revision": prepared.resolved_revision,
            "repetition": pair["repetition"],
            "pair_id": pair["pair_id"],
            "condition": attempt["condition"],
            "order_position": attempt["position"],
        }
        for field, expected_value in expected.items():
            if value.get(field) != expected_value:
                raise ExecutionError(f"retained artifact {field} differs: {path}")
        expected_pack = dict(benchmark_pack) if benchmark_pack else None
        if value.get("benchmark_pack") != expected_pack and (
            expected_pack is not None or "benchmark_pack" in value
        ):
            raise ExecutionError(f"retained artifact pack provenance differs: {path}")
        return value

    def _reconcile(
        self,
        state: dict[str, object],
        state_path: Path,
        prepared: Sequence[PreparedBenchmarkTask],
        tasks: Sequence[ExecutionTask],
        destination: Path,
        worktree_root: Path | None,
    ) -> None:
        changed = False
        for pair in state["pairs"]:  # type: ignore[union-attr]
            ready = prepared[pair["task_index"]]
            task = tasks[pair["task_index"]]
            complete_count = 0
            for attempt in pair["attempts"]:
                artifact_path = destination / _safe_artifact_path(attempt["artifact_path"])
                if attempt["status"] == "complete":
                    if not artifact_path.is_file():
                        raise ExecutionError(
                            f"completed attempt artifact is missing: {artifact_path}"
                        )
                    digest = _sha256(artifact_path.read_bytes())
                    if digest != attempt["artifact_sha256"]:
                        raise ExecutionError(
                            f"completed attempt artifact hash drift: {artifact_path}"
                        )
                    self._artifact(
                        artifact_path,
                        state=state,
                        pair=pair,
                        attempt=attempt,
                        prepared=ready,
                        benchmark_pack=task.benchmark_pack,
                    )
                    complete_count += 1
                    continue
                if artifact_path.exists():
                    self._artifact(
                        artifact_path,
                        state=state,
                        pair=pair,
                        attempt=attempt,
                        prepared=ready,
                        benchmark_pack=task.benchmark_pack,
                    )
                    attempt["artifact_sha256"] = _sha256(artifact_path.read_bytes())
                    attempt["status"] = "complete"
                    complete_count += 1
                    changed = True
                    continue
                if attempt["status"] == "running":
                    manager = WorktreeManager(ready.task.repository, root=worktree_root)
                    diagnostic = manager.diagnose(attempt["run_id"])
                    if diagnostic["status"] == "invalid":
                        raise ExecutionError(
                            f"cannot recover invalid lease {attempt['run_id']}: "
                            f"{diagnostic['detail']}"
                        )
                    if diagnostic["status"] in {"active", "stale"}:
                        try:
                            manager.recover(attempt["run_id"])
                        except WorktreeError as error:
                            raise ExecutionError(str(error)) from error
                    attempt["status"] = "pending"
                    changed = True
            new_status = (
                "complete" if complete_count == 2 else "partial" if complete_count else "pending"
            )
            if pair["status"] != new_status:
                pair["status"] = new_status
                changed = True
        state["usage"] = self._usage(state, prepared, tasks, destination)
        if changed:
            self._transition(state_path, state, "state_reconciled")

    def _usage(
        self,
        state: Mapping[str, object],
        prepared: Sequence[PreparedBenchmarkTask],
        tasks: Sequence[ExecutionTask],
        destination: Path,
    ) -> dict[str, object]:
        completed_pairs = 0
        attempts = 0
        runtime = 0.0
        tokens = 0
        for pair in state["pairs"]:  # type: ignore[union-attr]
            if pair["status"] == "complete":
                completed_pairs += 1
            ready = prepared[pair["task_index"]]
            task = tasks[pair["task_index"]]
            for attempt in pair["attempts"]:
                if attempt["status"] != "complete":
                    continue
                path = destination / attempt["artifact_path"]
                artifact = self._artifact(
                    path,
                    state=state,
                    pair=pair,
                    attempt=attempt,
                    prepared=ready,
                    benchmark_pack=task.benchmark_pack,
                )
                attempt_runtime, attempt_tokens = _artifact_usage(artifact)
                runtime += attempt_runtime
                tokens += attempt_tokens
                attempts += 1
        return {
            "completed_pairs": completed_pairs,
            "completed_attempts": attempts,
            "runtime_seconds": runtime,
            "total_tokens": tokens,
        }

    @staticmethod
    def _budget_reason(
        usage: Mapping[str, object], budget: ExecutionBudget, in_flight: int
    ) -> dict[str, object] | None:
        limits = (
            ("max_pairs", usage["completed_pairs"], budget.max_pairs),
            (
                "max_runtime_seconds",
                usage["runtime_seconds"],
                budget.max_runtime_seconds,
            ),
            ("max_total_tokens", usage["total_tokens"], budget.max_total_tokens),
        )
        for name, observed, threshold in limits:
            if threshold is not None and float(observed) >= float(threshold):
                return {
                    "kind": "budget_exhausted",
                    "budget": name,
                    "threshold": threshold,
                    "observed": observed,
                    "overshoot": max(0.0, float(observed) - float(threshold)),
                    "in_flight_pairs": in_flight,
                    "monetary_cost": None,
                }
        return None

    def _run_pairs(
        self,
        state: dict[str, object],
        state_path: Path,
        prepared: Sequence[PreparedBenchmarkTask],
        tasks: Sequence[ExecutionTask],
        destination: Path,
        worktree_root: Path | None,
        *,
        max_workers: int,
        budget: ExecutionBudget,
    ) -> None:
        pairs = state["pairs"]
        assert isinstance(pairs, list)
        partial = [pair for pair in pairs if pair["status"] == "partial"]
        pending = [pair for pair in pairs if pair["status"] == "pending"]
        queue = partial + pending
        futures: dict[Future[None], Mapping[str, object]] = {}
        stop_reason: dict[str, object] | None = None
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            while queue or futures:
                while queue and len(futures) < max_workers:
                    pair = queue[0]
                    is_partial = pair["status"] == "partial"
                    reason = self._budget_reason(state["usage"], budget, len(futures))
                    if not is_partial and reason is not None:
                        stop_reason = reason
                        break
                    if (
                        not is_partial
                        and budget.max_pairs is not None
                        and int(state["usage"]["completed_pairs"]) + len(futures)
                        >= budget.max_pairs
                    ):
                        stop_reason = {
                            "kind": "budget_exhausted",
                            "budget": "max_pairs",
                            "threshold": budget.max_pairs,
                            "observed": state["usage"]["completed_pairs"],
                            "overshoot": 0,
                            "in_flight_pairs": len(futures),
                            "monetary_cost": None,
                        }
                        break
                    queue.pop(0)
                    future = pool.submit(
                        self._run_pair,
                        state,
                        state_path,
                        pair,
                        prepared,
                        tasks,
                        destination,
                        worktree_root,
                    )
                    futures[future] = pair
                if not futures:
                    break
                completed, _pending = wait(tuple(futures), return_when=FIRST_COMPLETED)
                for future in completed:
                    futures.pop(future)
                    try:
                        future.result()
                    except Exception:
                        for pending_future in futures:
                            pending_future.cancel()
                        raise
                if stop_reason is None:
                    stop_reason = self._budget_reason(
                        state["usage"], budget, len(futures)
                    )
            if futures:
                wait(tuple(futures))

        remaining = [pair for pair in pairs if pair["status"] != "complete"]
        if remaining:
            state["status"] = "stopped"
            final_reason = stop_reason or {
                "kind": "execution_incomplete",
                "budget": None,
                "threshold": None,
                "observed": None,
                "overshoot": 0,
                "in_flight_pairs": 0,
                "monetary_cost": None,
            }
            if final_reason.get("budget") is not None:
                current = self._budget_reason(state["usage"], budget, 0)
                if current and current["budget"] == final_reason["budget"]:
                    final_reason = current
            state["stop_reason"] = final_reason
            self._transition(state_path, state, "execution_stopped")
        else:
            state["status"] = "completed"
            state["stop_reason"] = None
            self._transition(state_path, state, "execution_completed")

    def _run_pair(
        self,
        state: dict[str, object],
        state_path: Path,
        pair: dict[str, object],
        prepared: Sequence[PreparedBenchmarkTask],
        tasks: Sequence[ExecutionTask],
        destination: Path,
        worktree_root: Path | None,
    ) -> None:
        ready = prepared[pair["task_index"]]
        task = tasks[pair["task_index"]]
        with self._lock:
            pair["status"] = "running"
            self._transition(state_path, state, "pair_started")
        settings = state["settings"]
        assert isinstance(settings, Mapping)
        order = tuple(pair["order"])
        assert len(order) == 2
        for attempt in pair["attempts"]:
            if attempt["status"] == "complete":
                continue
            with self._lock:
                attempt["status"] = "running"
                self._transition(state_path, state, "attempt_started")
            artifact = self.runner.run_attempt(
                ready,
                output_dir=destination,
                experiment_id=str(state["experiment_id"]),
                repetition=int(pair["repetition"]),
                condition=str(attempt["condition"]),
                order=(str(order[0]), str(order[1])),
                position=int(attempt["position"]),
                sandbox=str(settings["sandbox"]),
                model=settings["model"] if isinstance(settings["model"], str) else None,
                codex_command=(
                    tuple(str(value) for value in settings["codex_command"])
                    if isinstance(settings["codex_command"], list)
                    else None
                ),
                context_timeout_seconds=float(settings["context_timeout_seconds"]),
                exact_command=tuple(str(value) for value in settings["exact_command"]),
                benchmark_pack=task.benchmark_pack,
                worktree_root=worktree_root,
                run_id=str(attempt["run_id"]),
                refuse_existing=True,
            )
            self._complete_attempt(
                state,
                state_path,
                pair,
                attempt,
                artifact,
                destination,
            )
        with self._lock:
            pair["status"] = "complete"
            state["usage"] = self._usage(state, prepared, tasks, destination)
            self._transition(state_path, state, "pair_completed")

    def _complete_attempt(
        self,
        state: dict[str, object],
        state_path: Path,
        pair: Mapping[str, object],
        attempt: dict[str, object],
        artifact: BenchmarkRunArtifact,
        destination: Path,
    ) -> None:
        path = destination / str(attempt["artifact_path"])
        if artifact.condition != attempt["condition"] or artifact.pair_id != pair["pair_id"]:
            raise ExecutionError("runner returned an artifact for the wrong attempt")
        with self._lock:
            attempt["artifact_sha256"] = _sha256(path.read_bytes())
            attempt["status"] = "complete"
            self._transition(state_path, state, "attempt_completed")


def diagnose_execution_state(path: str | Path) -> dict[str, object]:
    state = load_execution_state(path)
    worktree_root = state["worktree_root"]
    diagnostics = []
    for pair in state["pairs"]:  # type: ignore[union-attr]
        task = state["tasks"][pair["task_index"]]  # type: ignore[index]
        for attempt in pair["attempts"]:
            if attempt["status"] != "running":
                continue
            manager = WorktreeManager(task["repository"], root=worktree_root)
            diagnostics.append(manager.diagnose(attempt["run_id"]))
    return {
        "valid": True,
        "execution_id": state["execution_id"],
        "status": state["status"],
        "usage": state["usage"],
        "stop_reason": state["stop_reason"],
        "running_attempt_count": len(diagnostics),
        "lease_diagnostics": diagnostics,
    }


def recover_execution_state(path: str | Path) -> dict[str, object]:
    state_path = Path(path).resolve()
    state = load_execution_state(state_path)
    worktree_root = state["worktree_root"]
    recovered = []
    for pair in state["pairs"]:  # type: ignore[union-attr]
        task = state["tasks"][pair["task_index"]]  # type: ignore[index]
        complete_count = 0
        for attempt in pair["attempts"]:
            if attempt["status"] == "complete":
                complete_count += 1
                continue
            if attempt["status"] != "running":
                continue
            manager = WorktreeManager(task["repository"], root=worktree_root)
            diagnostic = manager.diagnose(attempt["run_id"])
            if diagnostic["status"] == "invalid":
                raise ExecutionError(
                    f"cannot recover invalid lease {attempt['run_id']}: "
                    f"{diagnostic['detail']}"
                )
            if diagnostic["status"] in {"active", "stale"}:
                manager.recover(attempt["run_id"])
                recovered.append(attempt["run_id"])
            attempt["status"] = "pending"
        pair["status"] = (
            "complete" if complete_count == 2 else "partial" if complete_count else "pending"
        )
    state["status"] = "stopped"
    state["stop_reason"] = {
        "kind": "manual_recovery",
        "budget": None,
        "threshold": None,
        "observed": None,
        "overshoot": 0,
        "in_flight_pairs": 0,
        "monetary_cost": None,
    }
    state["transition_count"] = int(state["transition_count"]) + 1
    _atomic_json(state_path, state)
    return {
        "valid": True,
        "execution_id": state["execution_id"],
        "recovered_run_ids": recovered,
        "recovered_count": len(recovered),
        "status": state["status"],
    }
