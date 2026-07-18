"""High-level bridge orchestration and stable exit codes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import IntEnum
from pathlib import Path
from uuid import uuid4

from .audit import AuditError, AuditLog
from .codex import CodexResult, CodexRunner, CodexStatus
from .git import FileChange, GitError, GitRepository, GitState
from .sigmap import ContextResult, ContextStatus, SigMapContextProvider
from .worktree import WorktreeError, WorktreeManager


class ExitCode(IntEnum):
    SUCCESS = 0
    INVALID_INPUT = 2
    SIGMAP_UNAVAILABLE = 20
    SIGMAP_INDEX_MISSING = 21
    SIGMAP_TIMEOUT = 22
    SIGMAP_FAILED = 23
    CODEX_UNAVAILABLE = 30
    CODEX_TIMEOUT = 31
    CODEX_MALFORMED_JSONL = 32
    CODEX_FAILED = 33
    GIT_FAILED = 40
    WORKTREE_FAILED = 41
    WORKTREE_CLEANUP_FAILED = 42
    AUDIT_FAILED = 43
    AUDIT_INVALID = 44


CONTEXT_EXIT_CODES = {
    ContextStatus.UNAVAILABLE: ExitCode.SIGMAP_UNAVAILABLE,
    ContextStatus.MISSING_INDEX: ExitCode.SIGMAP_INDEX_MISSING,
    ContextStatus.TIMED_OUT: ExitCode.SIGMAP_TIMEOUT,
    ContextStatus.FAILED: ExitCode.SIGMAP_FAILED,
}

CODEX_EXIT_CODES = {
    CodexStatus.SUCCEEDED: ExitCode.SUCCESS,
    CodexStatus.UNAVAILABLE: ExitCode.CODEX_UNAVAILABLE,
    CodexStatus.TIMED_OUT: ExitCode.CODEX_TIMEOUT,
    CodexStatus.MALFORMED_JSONL: ExitCode.CODEX_MALFORMED_JSONL,
    CodexStatus.FAILED: ExitCode.CODEX_FAILED,
}


@dataclass(frozen=True)
class BridgeResult:
    task: str
    repo_path: str
    requested_context: str
    context: ContextResult
    codex: CodexResult | None
    exit_code: ExitCode
    run_id: str | None = None
    base_commit: str | None = None
    source_dirty: bool | None = None
    execution_path: str | None = None
    changes: tuple[FileChange, ...] = ()
    worktree_cleaned: bool | None = None
    audit_entry_hash: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "task": self.task,
            "repo_path": self.repo_path,
            "requested_context": self.requested_context,
            "context_source": (
                "sigmap" if self.context.status is ContextStatus.READY else "none"
            ),
            "context": self.context.to_dict(),
            "codex": self.codex.to_dict() if self.codex else None,
            "exit_code": int(self.exit_code),
            "run_id": self.run_id,
            "base_commit": self.base_commit,
            "source_dirty": self.source_dirty,
            "execution_path": self.execution_path,
            "changes": [change.to_dict() for change in self.changes],
            "worktree_cleaned": self.worktree_cleaned,
            "audit_entry_hash": self.audit_entry_hash,
            "detail": self.detail,
        }


class Bridge:
    """Coordinate SigMap retrieval and one Codex execution."""

    def __init__(
        self,
        *,
        context_provider: SigMapContextProvider | None = None,
        codex_runner: CodexRunner | None = None,
        isolate_runs: bool = True,
        audit_runs: bool = True,
    ) -> None:
        self.context_provider = context_provider or SigMapContextProvider()
        self.codex_runner = codex_runner or CodexRunner()
        self.isolate_runs = isolate_runs
        self.audit_runs = audit_runs

    def run(
        self,
        task: str,
        repo_path: str | Path,
        *,
        use_sigmap: bool = True,
        sandbox: str = "workspace-write",
        worktree_root: str | Path | None = None,
        audit_path: str | Path | None = None,
    ) -> BridgeResult:
        repo = Path(repo_path).resolve()
        run_id = str(uuid4())
        if not task.strip() or not repo.is_dir():
            return BridgeResult(
                task=task,
                repo_path=str(repo),
                requested_context="sigmap" if use_sigmap else "none",
                context=ContextResult(
                    status=ContextStatus.FAILED,
                    detail="Task must be non-empty and repository must be a directory",
                ),
                codex=None,
                exit_code=ExitCode.INVALID_INPUT,
                run_id=run_id,
            )

        git_state: GitState | None = None
        if self.isolate_runs or self.audit_runs:
            try:
                git_state = GitRepository(repo).inspect()
                repo = Path(git_state.root)
            except GitError as error:
                return BridgeResult(
                    task=task,
                    repo_path=str(repo),
                    requested_context="sigmap" if use_sigmap else "none",
                    context=ContextResult.disabled(),
                    codex=None,
                    exit_code=ExitCode.GIT_FAILED,
                    run_id=run_id,
                    detail=str(error),
                )

        context = (
            self.context_provider.retrieve(task, repo)
            if use_sigmap
            else ContextResult.disabled()
        )
        if use_sigmap and context.status is not ContextStatus.READY:
            return BridgeResult(
                task=task,
                repo_path=str(repo),
                requested_context="sigmap",
                context=context,
                codex=None,
                exit_code=CONTEXT_EXIT_CODES[context.status],
                run_id=run_id,
                base_commit=git_state.base_commit if git_state else None,
                source_dirty=git_state.dirty if git_state else None,
            )

        execution_path = repo
        manager: WorktreeManager | None = None
        lease = None
        if self.isolate_runs:
            assert git_state is not None
            try:
                manager = WorktreeManager(repo, root=worktree_root)
                lease = manager.create(run_id, git_state.base_commit)
                execution_path = Path(lease.path)
            except WorktreeError as error:
                return BridgeResult(
                    task=task,
                    repo_path=str(repo),
                    requested_context="sigmap" if use_sigmap else "none",
                    context=context,
                    codex=None,
                    exit_code=ExitCode.WORKTREE_FAILED,
                    run_id=run_id,
                    base_commit=git_state.base_commit,
                    source_dirty=git_state.dirty,
                    detail=str(error),
                )

        codex: CodexResult | None = None
        changes: tuple[FileChange, ...] = ()
        exit_code = ExitCode.GIT_FAILED
        detail: str | None = None
        worktree_cleaned: bool | None = None
        try:
            codex = self.codex_runner.run(
                task,
                execution_path,
                context=context.context if use_sigmap else None,
                sandbox=sandbox,
            )
            exit_code = CODEX_EXIT_CODES[codex.status]
            if git_state is not None:
                changes = GitRepository(execution_path).changes()
        except GitError as error:
            detail = str(error)
        finally:
            if lease is not None and manager is not None:
                try:
                    manager.cleanup(lease)
                    worktree_cleaned = True
                except (WorktreeError, GitError) as error:
                    worktree_cleaned = False
                    exit_code = ExitCode.WORKTREE_CLEANUP_FAILED
                    detail = str(error)

        audit_entry_hash: str | None = None
        if self.audit_runs and git_state is not None and codex is not None:
            log = AuditLog(audit_path or repo / ".sigmap_bridge_audit.jsonl")
            try:
                audit_entry_hash = log.record(
                    run_id=run_id,
                    base_commit=git_state.base_commit,
                    condition="sigmap" if use_sigmap else "raw",
                    context=context.context if use_sigmap else "",
                    codex_thread_id=codex.thread_id,
                    exit_code=int(exit_code),
                    usage=asdict(codex.usage),
                    source_dirty=git_state.dirty,
                    changes=[change.to_dict() for change in changes],
                )
            except AuditError as error:
                exit_code = ExitCode.AUDIT_FAILED
                detail = str(error)

        return BridgeResult(
            task=task,
            repo_path=str(repo),
            requested_context="sigmap" if use_sigmap else "none",
            context=context,
            codex=codex,
            exit_code=exit_code,
            run_id=run_id,
            base_commit=git_state.base_commit if git_state else None,
            source_dirty=git_state.dirty if git_state else None,
            execution_path=str(execution_path),
            changes=changes,
            worktree_cleaned=worktree_cleaned,
            audit_entry_hash=audit_entry_hash,
            detail=detail,
        )
