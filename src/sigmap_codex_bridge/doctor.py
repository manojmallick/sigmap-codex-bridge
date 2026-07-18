"""Actionable local readiness diagnostics for live bridge runs."""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from .git import GitError, GitRepository
from .process import run_process


SUPPORTED_PYTHON = ((3, 10), (3, 14))
SUPPORTED_SYSTEMS = {"Darwin", "Linux"}


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    status: str
    detail: str
    fix: str | None = None
    required_for_live: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DoctorResult:
    live_ready: bool
    replay_ready: bool
    checks: tuple[DiagnosticCheck, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "live_ready": self.live_ready,
            "replay_ready": self.replay_ready,
            "checks": [check.to_dict() for check in self.checks],
        }


def _resolved_command(command: Sequence[str]) -> tuple[str, ...] | None:
    if not command:
        return None
    executable = command[0]
    if "/" in executable or "\\" in executable:
        path = Path(executable).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return (str(path.resolve()), *tuple(command[1:]))
        return None
    resolved = shutil.which(executable)
    return (resolved, *tuple(command[1:])) if resolved else None


def _codex_checks(command: Sequence[str], cwd: Path) -> list[DiagnosticCheck]:
    resolved = _resolved_command(command)
    if resolved is None:
        return [
            DiagnosticCheck(
                "codex_executable",
                "fail",
                f"Codex executable is unavailable: {command[0] if command else 'none'}",
                "Install Codex or pass --codex-command /path/to/codex.",
            ),
            DiagnosticCheck(
                "codex_auth",
                "fail",
                "Codex authentication cannot be checked without a working executable",
                "Install Codex, then run `codex login`.",
            ),
        ]
    version = run_process((*resolved, "--version"), cwd=cwd, timeout_seconds=10)
    if not version.ok:
        detail = version.stderr.strip() or version.launch_error or "version check failed"
        return [
            DiagnosticCheck(
                "codex_executable",
                "fail",
                f"Codex executable is broken: {detail}",
                "Reinstall Codex or pass a working --codex-command path.",
            ),
            DiagnosticCheck(
                "codex_auth",
                "fail",
                "Codex authentication cannot be checked because the executable failed",
                "Repair Codex, then run `codex login`.",
            ),
        ]
    version_text = version.stdout.strip() or version.stderr.strip()
    auth = run_process((*resolved, "login", "status"), cwd=cwd, timeout_seconds=10)
    auth_text = f"{auth.stdout}\n{auth.stderr}".strip()
    authenticated = auth.ok and any(
        marker in auth_text.lower()
        for marker in ("logged in", "authenticated", "chatgpt")
    )
    return [
        DiagnosticCheck("codex_executable", "ok", version_text or str(resolved[0])),
        DiagnosticCheck(
            "codex_auth",
            "ok" if authenticated else "fail",
            auth_text or "Codex did not confirm authentication",
            None if authenticated else "Run `codex login`, then retry doctor.",
        ),
    ]


def _sigmap_checks(command: Sequence[str], cwd: Path) -> list[DiagnosticCheck]:
    resolved = _resolved_command(command)
    if resolved is None:
        return [
            DiagnosticCheck(
                "sigmap_executable",
                "fail",
                f"SigMap executable is unavailable: {command[0] if command else 'none'}",
                "Install SigMap or pass --sigmap-command /path/to/sigmap.",
            ),
            DiagnosticCheck(
                "sigmap_index",
                "fail",
                "SigMap index cannot be checked without a working executable",
                "Install SigMap and run `sigmap` in the target repository.",
            ),
        ]
    process = run_process((*resolved, "doctor", "--json"), cwd=cwd, timeout_seconds=30)
    try:
        payload = json.loads(process.stdout)
        raw_checks = payload.get("checks", [])
    except (json.JSONDecodeError, AttributeError):
        payload = None
        raw_checks = []
    if not isinstance(payload, dict) or not isinstance(raw_checks, list):
        detail = process.stderr.strip() or process.launch_error or "invalid doctor output"
        return [
            DiagnosticCheck("sigmap_executable", "ok", str(resolved[0])),
            DiagnosticCheck(
                "sigmap_index",
                "fail",
                f"SigMap doctor failed: {detail}",
                "Run `sigmap doctor --json`, fix its errors, and regenerate with `sigmap`.",
            ),
        ]
    indexed = [
        item
        for item in raw_checks
        if isinstance(item, dict) and item.get("id") in {"context", "index"}
    ]
    stale = next(
        (
            item
            for item in raw_checks
            if isinstance(item, dict) and item.get("id") == "freshness"
        ),
        None,
    )
    index_ok = bool(indexed) and all(item.get("status") == "ok" for item in indexed)
    stale_status = stale.get("status") if isinstance(stale, dict) else "ok"
    status = "ok" if index_ok and stale_status == "ok" else (
        "warn" if index_ok else "fail"
    )
    details = [str(item.get("detail", "")) for item in indexed]
    if isinstance(stale, dict) and stale_status != "ok":
        details.append(str(stale.get("detail", "index is stale")))
    return [
        DiagnosticCheck("sigmap_executable", "ok", str(resolved[0])),
        DiagnosticCheck(
            "sigmap_index",
            status,
            "; ".join(detail for detail in details if detail) or "index status unknown",
            None if status == "ok" else "Run `sigmap` in the target repository.",
        ),
    ]


def run_doctor(
    repo_path: str | Path = ".",
    *,
    codex_command: Sequence[str] = ("codex",),
    sigmap_command: Sequence[str] = ("sigmap",),
) -> DoctorResult:
    repo = Path(repo_path).resolve()
    checks: list[DiagnosticCheck] = []
    current = sys.version_info[:2]
    python_ok = SUPPORTED_PYTHON[0] <= current <= SUPPORTED_PYTHON[1]
    checks.append(
        DiagnosticCheck(
            "python",
            "ok" if python_ok else "fail",
            f"Python {platform.python_version()}",
            None if python_ok else "Use Python 3.10 through 3.14.",
        )
    )
    system = platform.system()
    platform_ok = system in SUPPORTED_SYSTEMS
    checks.append(
        DiagnosticCheck(
            "platform",
            "ok" if platform_ok else "fail",
            f"{system} {platform.machine()}",
            None if platform_ok else "Use macOS or Linux for supported live runs.",
        )
    )

    git_path = shutil.which("git")
    checks.append(
        DiagnosticCheck(
            "git_executable",
            "ok" if git_path else "fail",
            git_path or "Git executable is unavailable",
            None if git_path else "Install Git and retry.",
        )
    )
    git_valid = False
    if git_path:
        try:
            state = GitRepository(repo).inspect()
            git_valid = True
            checks.append(DiagnosticCheck("git_repository", "ok", state.root))
            checks.append(
                DiagnosticCheck(
                    "git_clean",
                    "ok" if not state.dirty else "fail",
                    "working tree is clean"
                    if not state.dirty
                    else "working tree has uncommitted changes",
                    None if not state.dirty else "Commit or remove changes before a live run.",
                )
            )
        except (GitError, OSError) as error:
            checks.append(
                DiagnosticCheck(
                    "git_repository",
                    "fail",
                    str(error),
                    "Pass --repo for a valid Git repository.",
                )
            )
            checks.append(
                DiagnosticCheck(
                    "git_clean",
                    "fail",
                    "cleanliness cannot be checked outside a valid repository",
                )
            )
    if git_valid:
        checks.extend(_sigmap_checks(sigmap_command, repo))
        checks.extend(_codex_checks(codex_command, repo))
    else:
        checks.extend(_sigmap_checks(sigmap_command, Path.cwd()))
        checks.extend(_codex_checks(codex_command, Path.cwd()))

    live_ready = all(
        check.status == "ok" for check in checks if check.required_for_live
    )
    return DoctorResult(live_ready=live_ready, replay_ready=True, checks=tuple(checks))


def render_doctor(result: DoctorResult) -> str:
    lines = [
        f"Live readiness: {'READY' if result.live_ready else 'NOT READY'}",
        "Zero-credit replay: READY",
        "",
    ]
    icons = {"ok": "✓", "warn": "!", "fail": "✗"}
    for check in result.checks:
        lines.append(f"{icons.get(check.status, '?')} {check.name}: {check.detail}")
        if check.fix:
            lines.append(f"  Fix: {check.fix}")
    return "\n".join(lines)
