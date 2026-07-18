"""High-level bridge orchestration and stable exit codes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from .codex import CodexResult, CodexRunner, CodexStatus
from .sigmap import ContextResult, ContextStatus, SigMapContextProvider


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
        }


class Bridge:
    """Coordinate SigMap retrieval and one Codex execution."""

    def __init__(
        self,
        *,
        context_provider: SigMapContextProvider | None = None,
        codex_runner: CodexRunner | None = None,
    ) -> None:
        self.context_provider = context_provider or SigMapContextProvider()
        self.codex_runner = codex_runner or CodexRunner()

    def run(
        self,
        task: str,
        repo_path: str | Path,
        *,
        use_sigmap: bool = True,
        sandbox: str = "workspace-write",
    ) -> BridgeResult:
        repo = Path(repo_path).resolve()
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
            )

        codex = self.codex_runner.run(
            task,
            repo,
            context=context.context if use_sigmap else None,
            sandbox=sandbox,
        )
        return BridgeResult(
            task=task,
            repo_path=str(repo),
            requested_context="sigmap" if use_sigmap else "none",
            context=context,
            codex=codex,
            exit_code=CODEX_EXIT_CODES[codex.status],
        )
