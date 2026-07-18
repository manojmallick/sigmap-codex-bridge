"""Command-line interface for SigMap Codex Bridge."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence

from .bridge import Bridge, BridgeResult


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
    lines.append(f"Exit code: {int(result.exit_code)}")
    return "\n".join(lines)


def main(
    argv: Sequence[str] | None = None,
    *,
    bridge_factory: Callable[[], Bridge] = Bridge,
) -> int:
    args = build_parser().parse_args(argv)
    bridge = bridge_factory()
    result = bridge.run(
        args.task,
        args.repo,
        use_sigmap=not args.no_sigmap,
        sandbox=args.sandbox,
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(_human_result(result))
    return int(result.exit_code)
