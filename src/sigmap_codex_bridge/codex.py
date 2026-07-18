"""Codex JSONL execution and parsing contract."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from .process import ProcessResult, run_process


class CodexStatus(str, Enum):
    SUCCEEDED = "succeeded"
    UNAVAILABLE = "unavailable"
    TIMED_OUT = "timed_out"
    MALFORMED_JSONL = "malformed_jsonl"
    FAILED = "failed"


@dataclass(frozen=True)
class CodexUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0


@dataclass(frozen=True)
class CodexResult:
    status: CodexStatus
    process: ProcessResult
    thread_id: str | None = None
    final_message: str | None = None
    file_changes: tuple[str, ...] = ()
    usage: CodexUsage = field(default_factory=CodexUsage)
    event_count: int = 0
    detail: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "thread_id": self.thread_id,
            "final_message": self.final_message,
            "file_changes": list(self.file_changes),
            "usage": asdict(self.usage),
            "event_count": self.event_count,
            "detail": self.detail,
            "process": self.process.to_dict(),
        }


def _usage_from_event(event: Mapping[str, Any]) -> CodexUsage:
    raw = event.get("usage")
    if not isinstance(raw, Mapping):
        return CodexUsage()
    return CodexUsage(
        input_tokens=int(raw.get("input_tokens", 0)),
        cached_input_tokens=int(raw.get("cached_input_tokens", 0)),
        output_tokens=int(raw.get("output_tokens", 0)),
        reasoning_output_tokens=int(raw.get("reasoning_output_tokens", 0)),
    )


def _file_change_paths(item: Mapping[str, Any]) -> set[str]:
    paths: set[str] = set()
    direct_path = item.get("path") or item.get("file_path")
    if isinstance(direct_path, str):
        paths.add(direct_path)

    changes = item.get("changes")
    if isinstance(changes, list):
        for change in changes:
            if not isinstance(change, Mapping):
                continue
            path = change.get("path") or change.get("file_path")
            if isinstance(path, str):
                paths.add(path)
    return paths


def parse_codex_jsonl(process: ProcessResult) -> CodexResult:
    """Parse a completed Codex process into a stable result contract."""

    if process.timed_out:
        return CodexResult(
            status=CodexStatus.TIMED_OUT,
            process=process,
            detail="Codex execution timed out",
        )
    if process.launch_error is not None:
        return CodexResult(
            status=CodexStatus.UNAVAILABLE,
            process=process,
            detail=process.launch_error,
        )

    events: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(process.stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            return CodexResult(
                status=CodexStatus.MALFORMED_JSONL,
                process=process,
                event_count=len(events),
                detail=f"Invalid JSONL at line {line_number}: {error.msg}",
            )
        if not isinstance(event, Mapping):
            return CodexResult(
                status=CodexStatus.MALFORMED_JSONL,
                process=process,
                event_count=len(events),
                detail=f"JSONL line {line_number} is not an object",
            )
        events.append(event)

    thread_id: str | None = None
    final_message: str | None = None
    file_changes: set[str] = set()
    usage = CodexUsage()
    completed = False
    failure_detail: str | None = None

    for event in events:
        event_type = event.get("type")
        if event_type == "thread.started" and isinstance(event.get("thread_id"), str):
            thread_id = event["thread_id"]
        elif event_type == "item.completed":
            item = event.get("item")
            if not isinstance(item, Mapping):
                continue
            if item.get("type") == "agent_message" and isinstance(
                item.get("text"), str
            ):
                final_message = item["text"]
            elif item.get("type") == "file_change":
                file_changes.update(_file_change_paths(item))
        elif event_type == "turn.completed":
            completed = True
            usage = _usage_from_event(event)
        elif event_type in {"turn.failed", "error"}:
            raw_detail = event.get("message") or event.get("error")
            failure_detail = (
                str(raw_detail) if raw_detail else f"Codex emitted {event_type}"
            )

    if process.returncode != 0:
        return CodexResult(
            status=CodexStatus.FAILED,
            process=process,
            thread_id=thread_id,
            final_message=final_message,
            file_changes=tuple(sorted(file_changes)),
            usage=usage,
            event_count=len(events),
            detail=failure_detail or f"Codex exited with status {process.returncode}",
        )
    if failure_detail is not None:
        return CodexResult(
            status=CodexStatus.FAILED,
            process=process,
            thread_id=thread_id,
            final_message=final_message,
            file_changes=tuple(sorted(file_changes)),
            usage=usage,
            event_count=len(events),
            detail=failure_detail,
        )
    if not completed:
        return CodexResult(
            status=CodexStatus.MALFORMED_JSONL,
            process=process,
            thread_id=thread_id,
            final_message=final_message,
            file_changes=tuple(sorted(file_changes)),
            event_count=len(events),
            detail="JSONL stream ended without turn.completed",
        )
    return CodexResult(
        status=CodexStatus.SUCCEEDED,
        process=process,
        thread_id=thread_id,
        final_message=final_message,
        file_changes=tuple(sorted(file_changes)),
        usage=usage,
        event_count=len(events),
    )


class CodexRunner:
    """Run Codex with task-as-prompt and optional context-as-stdin."""

    def __init__(
        self,
        *,
        command: Sequence[str] = ("codex",),
        timeout_seconds: float = 900.0,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.command = tuple(command)
        self.timeout_seconds = timeout_seconds
        self.env = env

    def run(
        self,
        task: str,
        repo_path: str | Path,
        *,
        context: str | None,
        sandbox: str,
    ) -> CodexResult:
        process = run_process(
            (
                *self.command,
                "exec",
                "--json",
                "--sandbox",
                sandbox,
                task,
            ),
            cwd=repo_path,
            input_text=context,
            timeout_seconds=self.timeout_seconds,
            env=self.env,
        )
        return parse_codex_jsonl(process)
