"""Command-line interface for SigMap Codex Bridge."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path

from .audit import AuditLog
from .bridge import Bridge, BridgeResult, ExitCode
from .git import GitError
from .worktree import WorktreeError, WorktreeManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sigmap-bridge",
        description="Run Codex with explicit raw or SigMap-ranked context",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run one bridge task")
    run_parser.add_argument("task", help="Task instruction passed to Codex")
    run_parser.add_argument("--repo", default=".", help="Target Git repository")
    run_parser.add_argument(
        "--no-sigmap",
        action="store_true",
        help="Run the explicit raw condition without SigMap context",
    )
    run_parser.add_argument(
        "--sandbox",
        choices=("read-only", "workspace-write", "danger-full-access"),
        default="workspace-write",
        help="Explicit Codex sandbox policy",
    )
    run_parser.add_argument(
        "--json", action="store_true", help="Emit the complete result as JSON"
    )
    run_parser.add_argument(
        "--worktree-root", help="Override the bridge-owned worktree root"
    )
    run_parser.add_argument("--audit-log", help="Override the audit JSONL path")

    verify_parser = subparsers.add_parser(
        "verify", help="Verify the audit chain and checkpoint"
    )
    verify_parser.add_argument("--repo", default=".", help="Repository root")
    verify_parser.add_argument("--audit-log", help="Override the audit JSONL path")
    verify_parser.add_argument("--json", action="store_true")

    cleanup_parser = subparsers.add_parser(
        "cleanup", help="Recover one interrupted bridge worktree lease"
    )
    cleanup_parser.add_argument("run_id", help="Exact bridge run ID to clean")
    cleanup_parser.add_argument("--repo", default=".", help="Source repository")
    cleanup_parser.add_argument("--worktree-root", help="Managed worktree root")
    cleanup_parser.add_argument("--json", action="store_true")
    return parser


def _human_result(result: BridgeResult) -> str:
    lines = [
        f"Task: {result.task}",
        f"Repository: {result.repo_path}",
        f"Requested context: {result.requested_context}",
        f"Context status: {result.context.status.value}",
    ]
    if result.context.detail:
        lines.append(f"Context detail: {result.context.detail}")
    if result.codex is not None:
        lines.extend(
            (
                f"Codex status: {result.codex.status.value}",
                f"Codex thread: {result.codex.thread_id or 'none'}",
                f"Files changed: {', '.join(result.codex.file_changes) or 'none'}",
            )
        )
        if result.codex.detail:
            lines.append(f"Codex detail: {result.codex.detail}")
    if result.base_commit:
        lines.append(f"Base commit: {result.base_commit}")
    if result.run_id:
        lines.append(f"Run ID: {result.run_id}")
    if result.worktree_cleaned is not None:
        lines.append(f"Worktree cleaned: {result.worktree_cleaned}")
    if result.audit_entry_hash:
        lines.append(f"Audit entry: {result.audit_entry_hash}")
    if result.detail:
        lines.append(f"Detail: {result.detail}")
    lines.append(f"Exit code: {int(result.exit_code)}")
    return "\n".join(lines)


def _print_payload(payload: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")


def main(
    argv: Sequence[str] | None = None,
    *,
    bridge_factory: Callable[[], Bridge] = Bridge,
) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "verify":
        repo = Path(args.repo).resolve()
        verification = AuditLog(
            args.audit_log or repo / ".sigmap_bridge_audit.jsonl"
        ).verify()
        payload = verification.to_dict()
        _print_payload(payload, as_json=args.json)
        return (
            int(ExitCode.SUCCESS) if verification.valid else int(ExitCode.AUDIT_INVALID)
        )

    if args.command == "cleanup":
        try:
            lease = WorktreeManager(args.repo, root=args.worktree_root).recover(
                args.run_id
            )
            payload: dict[str, object] = {
                "cleaned": True,
                "run_id": lease.run_id,
                "path": lease.path,
            }
            exit_code = 0
        except (GitError, WorktreeError) as error:
            payload = {
                "cleaned": False,
                "run_id": args.run_id,
                "error": str(error),
            }
            exit_code = int(ExitCode.WORKTREE_CLEANUP_FAILED)
        _print_payload(payload, as_json=args.json)
        return exit_code

    bridge = bridge_factory()
    result = bridge.run(
        args.task,
        args.repo,
        use_sigmap=not args.no_sigmap,
        sandbox=args.sandbox,
        worktree_root=args.worktree_root,
        audit_path=args.audit_log,
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(_human_result(result))
    return int(result.exit_code)
