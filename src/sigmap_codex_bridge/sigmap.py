"""SigMap context retrieval contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence

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


class SigMapContextProvider:
    """Retrieve ranked context using the SigMap CLI."""

    def __init__(
        self,
        *,
        command: Sequence[str] = ("npx", "sigmap"),
        top: int = 8,
        timeout_seconds: float = 30.0,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.command = tuple(command)
        self.top = top
        self.timeout_seconds = timeout_seconds
        self.env = env

    def retrieve(self, task: str, repo_path: str | Path) -> ContextResult:
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

        context = process.stdout.strip()
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
