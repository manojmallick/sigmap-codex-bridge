"""Scoped, recoverable Git worktree leases."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .git import GitError, GitRepository
from .process import run_process


RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class WorktreeError(RuntimeError):
    """Raised when a worktree lease cannot be safely created or removed."""


@dataclass(frozen=True)
class WorktreeLease:
    run_id: str
    source_repo: str
    base_commit: str
    path: str
    state: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class WorktreeManager:
    def __init__(
        self,
        source_repo: str | Path,
        *,
        root: str | Path | None = None,
    ) -> None:
        self.source_repo = GitRepository(source_repo).root()
        self.root = (
            Path(root).resolve()
            if root is not None
            else self.source_repo / ".bridge-worktrees"
        )
        self.runs_dir = self.root / "runs"
        self.leases_dir = self.root / "leases"

    def _validate_run_id(self, run_id: str) -> None:
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise WorktreeError("Invalid run ID")

    def _lease_path(self, run_id: str) -> Path:
        self._validate_run_id(run_id)
        return self.leases_dir / f"{run_id}.json"

    def _run_path(self, run_id: str) -> Path:
        self._validate_run_id(run_id)
        return self.runs_dir / run_id

    def _write_lease(self, lease: WorktreeLease) -> None:
        try:
            _atomic_json(self._lease_path(lease.run_id), lease.to_dict())
        except OSError as error:
            raise WorktreeError(f"Cannot write worktree lease: {error}") from error

    def _read_lease(self, run_id: str) -> WorktreeLease:
        lease_path = self._lease_path(run_id)
        try:
            value = json.loads(lease_path.read_text(encoding="utf-8"))
            lease = WorktreeLease(**value)
        except (OSError, json.JSONDecodeError, TypeError) as error:
            raise WorktreeError(f"Cannot read worktree lease: {error}") from error
        self._validate_lease(lease)
        return lease

    def _validate_lease(self, lease: WorktreeLease) -> None:
        expected_path = self._run_path(lease.run_id).resolve()
        if Path(lease.source_repo).resolve() != self.source_repo:
            raise WorktreeError("Lease source repository does not match")
        if Path(lease.path).resolve() != expected_path:
            raise WorktreeError("Lease path is outside the managed run directory")
        if expected_path.parent != self.runs_dir.resolve():
            raise WorktreeError("Lease path failed containment validation")

    def create(self, run_id: str, base_commit: str) -> WorktreeLease:
        path = self._run_path(run_id).resolve()
        lease_path = self._lease_path(run_id)
        if path.exists() or lease_path.exists():
            raise WorktreeError(f"Run ID already has a worktree lease: {run_id}")

        creating = WorktreeLease(
            run_id=run_id,
            source_repo=str(self.source_repo),
            base_commit=base_commit,
            path=str(path),
            state="creating",
        )
        self._write_lease(creating)
        path.parent.mkdir(parents=True, exist_ok=True)
        result = run_process(
            (
                "git",
                "-C",
                str(self.source_repo),
                "worktree",
                "add",
                "--detach",
                str(path),
                base_commit,
            ),
            cwd=self.source_repo,
            timeout_seconds=60,
        )
        if not result.ok:
            detail = result.stderr.strip() or result.launch_error or "unknown error"
            raise WorktreeError(
                f"Cannot create worktree for recoverable lease {run_id}: {detail}"
            )

        active = WorktreeLease(
            run_id=run_id,
            source_repo=str(self.source_repo),
            base_commit=base_commit,
            path=str(path),
            state="active",
        )
        self._write_lease(active)
        return active

    def cleanup(self, lease: WorktreeLease) -> None:
        self._validate_lease(lease)
        stored = self._read_lease(lease.run_id)
        if stored != lease:
            raise WorktreeError("Lease changed since it was acquired")

        path = Path(lease.path)
        if path.exists():
            result = run_process(
                (
                    "git",
                    "-C",
                    str(self.source_repo),
                    "worktree",
                    "remove",
                    "--force",
                    str(path),
                ),
                cwd=self.source_repo,
                timeout_seconds=60,
            )
            if not result.ok:
                detail = result.stderr.strip() or result.launch_error or "unknown error"
                raise WorktreeError(f"Cannot remove leased worktree: {detail}")

        prune = run_process(
            ("git", "-C", str(self.source_repo), "worktree", "prune"),
            cwd=self.source_repo,
            timeout_seconds=30,
        )
        if not prune.ok:
            raise GitError(prune.stderr.strip() or "git worktree prune failed")
        self._lease_path(lease.run_id).unlink(missing_ok=True)

    def recover(self, run_id: str) -> WorktreeLease:
        lease = self._read_lease(run_id)
        self.cleanup(lease)
        return lease

    def diagnose(self, run_id: str) -> dict[str, object]:
        """Inspect one exact managed lease without changing repository state."""

        lease_path = self._lease_path(run_id)
        expected_path = self._run_path(run_id).resolve()
        if not lease_path.exists():
            return {
                "run_id": run_id,
                "status": "missing",
                "lease_path": str(lease_path),
                "worktree_path": str(expected_path),
                "path_exists": expected_path.exists(),
                "git_registered": False,
                "detail": "no bridge-owned lease file exists",
            }
        try:
            lease = self._read_lease(run_id)
        except WorktreeError as error:
            return {
                "run_id": run_id,
                "status": "invalid",
                "lease_path": str(lease_path),
                "worktree_path": str(expected_path),
                "path_exists": expected_path.exists(),
                "git_registered": False,
                "detail": str(error),
            }
        listed = run_process(
            ("git", "-C", str(self.source_repo), "worktree", "list", "--porcelain"),
            cwd=self.source_repo,
            timeout_seconds=30,
        )
        registered = listed.ok and f"worktree {expected_path}" in listed.stdout.splitlines()
        path_exists = expected_path.exists()
        if path_exists and registered:
            status = "active"
            detail = f"lease is {lease.state} and its worktree is registered"
        else:
            status = "stale"
            detail = "lease exists but its worktree path or Git registration is missing"
        return {
            "run_id": run_id,
            "status": status,
            "lease_path": str(lease_path),
            "worktree_path": str(expected_path),
            "path_exists": path_exists,
            "git_registered": registered,
            "detail": detail,
        }
