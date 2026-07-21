"""SigMap context retrieval contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Protocol, Sequence, runtime_checkable

from .process import ProcessResult, run_process


class ContextStatus(str, Enum):
    DISABLED = "disabled"
    READY = "ready"
    MISSING_INDEX = "missing_index"
    UNAVAILABLE = "unavailable"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


@dataclass(frozen=True)
class ContextResult:
    status: ContextStatus
    context: str = ""
    detail: str | None = None
    process: ProcessResult | None = None

    @classmethod
    def disabled(cls) -> "ContextResult":
        return cls(status=ContextStatus.DISABLED)

    @property
    def word_count(self) -> int:
        return len(self.context.split())

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "context_supplied": self.status is ContextStatus.READY,
            "context_words": self.word_count,
            "detail": self.detail,
            "process": self.process.to_dict() if self.process else None,
        }


@runtime_checkable
class ContextProvider(Protocol):
    """Public extension contract for ranked repository-context providers."""

    name: str

    def retrieve(self, task: str, repo_path: str | Path) -> ContextResult:
        """Return ready context or an explicit fail-closed status."""


class RawContextProvider:
    """Built-in provider for the explicit no-context control condition."""

    name = "raw"

    def retrieve(self, task: str, repo_path: str | Path) -> ContextResult:
        del task, repo_path
        return ContextResult.disabled()


class SigMapContextProvider:
    """Retrieve ranked context using the SigMap CLI."""

    name = "sigmap"

    def __init__(
        self,
        *,
        command: Sequence[str] = ("sigmap",),
        top: int = 8,
        timeout_seconds: float = 30.0,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.command = tuple(command)
        self.top = top
        self.timeout_seconds = timeout_seconds
        self.env = env

    def retrieve(self, task: str, repo_path: str | Path) -> ContextResult:
        context_path = Path(repo_path) / ".context" / "query-context.md"
        try:
            before_context = (
                (context_path.stat().st_mtime_ns, context_path.stat().st_size)
                if context_path.is_file()
                else None
            )
        except OSError:
            before_context = None
        process = run_process(
            (
                *self.command,
                "ask",
                task,
                "--top",
                str(self.top),
                "--no-squeeze",
            ),
            cwd=repo_path,
            timeout_seconds=self.timeout_seconds,
            env=self.env,
        )

        if process.timed_out:
            return ContextResult(
                status=ContextStatus.TIMED_OUT,
                detail="SigMap context retrieval timed out",
                process=process,
            )
        if process.launch_error is not None:
            return ContextResult(
                status=ContextStatus.UNAVAILABLE,
                detail=process.launch_error,
                process=process,
            )

        diagnostic = f"{process.stdout}\n{process.stderr}".lower()
        missing_markers = (
            "no context file found",
            "no signatures indexed",
            "run: sigmap",
            "run: npx sigmap",
        )
        if any(marker in diagnostic for marker in missing_markers):
            return ContextResult(
                status=ContextStatus.MISSING_INDEX,
                detail="SigMap index is missing or empty",
                process=process,
            )
        if process.returncode != 0:
            return ContextResult(
                status=ContextStatus.FAILED,
                detail=f"SigMap exited with status {process.returncode}",
                process=process,
            )

        try:
            after_context = (
                (context_path.stat().st_mtime_ns, context_path.stat().st_size)
                if context_path.is_file()
                else None
            )
            context = (
                context_path.read_text(encoding="utf-8").strip()
                if after_context is not None and after_context != before_context
                else process.stdout.strip()
            )
        except OSError as error:
            return ContextResult(
                status=ContextStatus.FAILED,
                detail=f"Cannot read SigMap query context: {error}",
                process=process,
            )
        if not context:
            return ContextResult(
                status=ContextStatus.FAILED,
                detail="SigMap returned empty context",
                process=process,
            )
        return ContextResult(
            status=ContextStatus.READY,
            context=context,
            process=process,
        )
