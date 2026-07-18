"""Isolated validation of benchmark source revisions and baseline commands."""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from .benchmark import BenchmarkTask
from .git import GitError, GitRepository
from .process import ProcessResult, run_process
from .worktree import WorktreeError, WorktreeLease, WorktreeManager


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class PreflightResult:
    valid: bool
    revision: str | None
    checks: tuple[PreflightCheck, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "revision": self.revision,
            "checks": [asdict(check) for check in self.checks],
        }


def _resolve_revision(repository: Path, revision: str) -> str | None:
    result = run_process(
        ("git", "-C", str(repository), "rev-parse", "--verify", f"{revision}^{{commit}}"),
        cwd=repository,
        timeout_seconds=30,
    )
    return result.stdout.strip() if result.ok else None


def _executable_available(command: tuple[str, ...], cwd: Path) -> bool:
    executable = command[0]
    if "/" in executable or "\\" in executable:
        path = Path(executable)
        if not path.is_absolute():
            path = cwd / path
        return path.is_file() and os.access(path, os.X_OK)
    return shutil.which(executable) is not None


def _run(command: tuple[str, ...], cwd: Path, timeout: float) -> ProcessResult:
    return run_process(command, cwd=cwd, timeout_seconds=timeout)


def preflight_task(
    task: BenchmarkTask,
    *,
    worktree_root: str | Path | None = None,
) -> PreflightResult:
    """Reject invalid sources and already-failing baselines in isolation."""

    checks: list[PreflightCheck] = []
    repository = Path(task.repository)
    try:
        state = GitRepository(repository).inspect()
    except (GitError, OSError) as error:
        checks.append(PreflightCheck("repository", False, str(error)))
        return PreflightResult(False, None, tuple(checks))

    checks.append(PreflightCheck("repository", True, state.root))
    if state.dirty:
        checks.append(
            PreflightCheck("source_clean", False, "source repository has changes")
        )
        return PreflightResult(False, None, tuple(checks))
    checks.append(PreflightCheck("source_clean", True, "source repository is clean"))

    resolved_revision = _resolve_revision(repository, task.revision)
    if resolved_revision is None:
        checks.append(
            PreflightCheck("revision", False, f"revision not found: {task.revision}")
        )
        return PreflightResult(False, None, tuple(checks))
    checks.append(PreflightCheck("revision", True, resolved_revision))

    manager = WorktreeManager(repository, root=worktree_root)
    lease: WorktreeLease | None = None
    can_run_tests = True
    try:
        run_id = f"benchmark-preflight-{uuid.uuid4().hex}"
        lease = manager.create(run_id, resolved_revision)
        worktree = Path(lease.path)
        checks.append(PreflightCheck("worktree", True, lease.path))

        if task.setup_command is not None:
            if not _executable_available(task.setup_command, worktree):
                checks.append(
                    PreflightCheck(
                        "setup_command", False, "setup executable is unavailable"
                    )
                )
                can_run_tests = False
            else:
                setup = _run(task.setup_command, worktree, task.timeout_seconds)
                checks.append(
                    PreflightCheck(
                        "setup_command",
                        setup.ok,
                        "setup passed" if setup.ok else "setup failed",
                    )
                )
                can_run_tests = setup.ok
                if setup.ok:
                    setup_changes = GitRepository(worktree).changes()
                    setup_clean = not setup_changes
                    checks.append(
                        PreflightCheck(
                            "setup_clean",
                            setup_clean,
                            "setup left no Git-visible changes"
                            if setup_clean
                            else "setup left Git-visible changes",
                        )
                    )
                    can_run_tests = setup_clean

        if can_run_tests:
            commands = (task.test_command, *task.static_check_commands)
            unavailable = [
                command[0]
                for command in commands
                if not _executable_available(command, worktree)
            ]
            if unavailable:
                checks.append(
                    PreflightCheck(
                        "commands_available",
                        False,
                        f"unavailable executables: {', '.join(unavailable)}",
                    )
                )
                can_run_tests = False
            else:
                checks.append(
                    PreflightCheck(
                        "commands_available", True, "all executables are available"
                    )
                )

        if can_run_tests:
            baseline = _run(task.test_command, worktree, task.timeout_seconds)
            checks.append(
                PreflightCheck(
                    "baseline_tests",
                    baseline.ok,
                    "baseline tests pass"
                    if baseline.ok
                    else "baseline tests fail or cannot complete",
                )
            )
    except (GitError, WorktreeError, OSError) as error:
        checks.append(PreflightCheck("worktree", False, str(error)))
    finally:
        if lease is not None:
            try:
                manager.cleanup(lease)
                checks.append(PreflightCheck("cleanup", True, "worktree removed"))
            except (GitError, WorktreeError, OSError) as error:
                checks.append(PreflightCheck("cleanup", False, str(error)))

    return PreflightResult(
        all(check.passed for check in checks),
        resolved_revision,
        tuple(checks),
    )
