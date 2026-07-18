"""Typed, shell-free subprocess execution."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ProcessResult:
    """Complete observable result of one child process invocation."""

    command: tuple[str, ...]
    cwd: str
    stdout: str
    stderr: str
    returncode: int | None
    duration_seconds: float
    timed_out: bool = False
    launch_error: str | None = None

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and self.launch_error is None

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["command"] = list(self.command)
        return value


def _stream_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def run_process(
    command: Sequence[str],
    *,
    cwd: str | Path,
    input_text: str | None = None,
    timeout_seconds: float = 30.0,
    env: Mapping[str, str] | None = None,
) -> ProcessResult:
    """Run a command without a shell and capture every relevant outcome."""

    argv = tuple(str(part) for part in command)
    resolved_cwd = str(Path(cwd).resolve())
    child_env = None
    if env is not None:
        child_env = os.environ.copy()
        child_env.update(env)

    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(argv),
            cwd=resolved_cwd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=child_env,
            shell=False,
        )
        return ProcessResult(
            command=argv,
            cwd=resolved_cwd,
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
            duration_seconds=round(time.monotonic() - started, 6),
        )
    except subprocess.TimeoutExpired as error:
        return ProcessResult(
            command=argv,
            cwd=resolved_cwd,
            stdout=_stream_text(error.stdout),
            stderr=_stream_text(error.stderr),
            returncode=None,
            duration_seconds=round(time.monotonic() - started, 6),
            timed_out=True,
            launch_error="timeout",
        )
    except FileNotFoundError as error:
        return ProcessResult(
            command=argv,
            cwd=resolved_cwd,
            stdout="",
            stderr=str(error),
            returncode=None,
            duration_seconds=round(time.monotonic() - started, 6),
            launch_error="executable_not_found",
        )
    except OSError as error:
        return ProcessResult(
            command=argv,
            cwd=resolved_cwd,
            stdout="",
            stderr=str(error),
            returncode=None,
            duration_seconds=round(time.monotonic() - started, 6),
            launch_error="launch_error",
        )
