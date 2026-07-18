"""Command-line interface for SigMap Codex Bridge."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from .audit import AuditLog
from .benchmark import BenchmarkValidationError, load_benchmark_task
from .bridge import Bridge, BridgeResult, ExitCode
from .demo import DemoError, render_replay, replay_demo
from .doctor import render_doctor, run_doctor
from .experiment import (
    BenchmarkRunError,
    PairedBenchmarkRunner,
    default_exact_command,
)
from .git import GitError
from .preflight import preflight_task
from .reporting import ReportError, write_report
from .worktree import WorktreeError, WorktreeManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sigmap-bridge",
        description="Run Codex with explicit raw or SigMap-ranked context",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo_parser = subparsers.add_parser(
        "demo", help="Replay packaged measured results without live calls"
    )
    demo_parser.add_argument("--json", action="store_true")

    doctor_parser = subparsers.add_parser(
        "doctor", help="Diagnose local readiness for live bridge runs"
    )
    doctor_parser.add_argument("--repo", default=".", help="Target Git repository")
    doctor_parser.add_argument("--codex-command", default="codex")
    doctor_parser.add_argument("--sigmap-command", default="sigmap")
    doctor_parser.add_argument(
        "--require-live",
        action="store_true",
        help="Return a nonzero exit when live-run requirements are not ready",
    )
    doctor_parser.add_argument("--json", action="store_true")

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

    benchmark_parser = subparsers.add_parser(
        "benchmark", help="Validate and preflight benchmark task specifications"
    )
    benchmark_subparsers = benchmark_parser.add_subparsers(
        dest="benchmark_command", required=True
    )
    validate_parser = benchmark_subparsers.add_parser(
        "validate", help="Validate a YAML or JSON benchmark task"
    )
    validate_parser.add_argument("task_file")
    validate_parser.add_argument("--json", action="store_true")
    preflight_parser = benchmark_subparsers.add_parser(
        "preflight", help="Check a benchmark baseline in an isolated worktree"
    )
    preflight_parser.add_argument("task_file")
    preflight_parser.add_argument("--worktree-root")
    preflight_parser.add_argument("--json", action="store_true")
    benchmark_run_parser = benchmark_subparsers.add_parser(
        "run", help="Run reproducible paired raw and SigMap conditions"
    )
    benchmark_run_parser.add_argument("task_files", nargs="+")
    benchmark_run_parser.add_argument(
        "--experiment-id", required=True, help="Stable experiment identifier"
    )
    benchmark_run_parser.add_argument(
        "--output-dir", default="benchmark_runs", help="Raw artifact directory"
    )
    benchmark_run_parser.add_argument(
        "--start-condition", choices=("raw", "sigmap"), default="raw"
    )
    benchmark_run_parser.add_argument(
        "--sandbox",
        choices=("read-only", "workspace-write", "danger-full-access"),
        default="workspace-write",
    )
    benchmark_run_parser.add_argument("--model")
    benchmark_run_parser.add_argument(
        "--codex-command", help="Path to the Codex executable"
    )
    benchmark_run_parser.add_argument(
        "--context-timeout",
        type=float,
        default=120.0,
        help="SigMap retrieval timeout in seconds",
    )
    benchmark_run_parser.add_argument("--worktree-root")
    benchmark_run_parser.add_argument("--json", action="store_true")
    report_parser = benchmark_subparsers.add_parser(
        "report", help="Regenerate JSON and Markdown reports from raw artifacts"
    )
    report_parser.add_argument("artifact_dir")
    report_parser.add_argument("--json-output")
    report_parser.add_argument("--markdown-output")
    report_parser.add_argument("--json", action="store_true")
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
    benchmark_runner_factory: Callable[[], PairedBenchmarkRunner] = PairedBenchmarkRunner,
) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "demo":
        try:
            payload = replay_demo()
        except DemoError as error:
            payload = {
                "replay": True,
                "live_calls": 0,
                "valid": False,
                "error": str(error),
            }
            _print_payload(payload, as_json=args.json)
            return int(ExitCode.INVALID_INPUT)
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(render_replay(payload))
        return int(ExitCode.SUCCESS)

    if args.command == "doctor":
        result = run_doctor(
            args.repo,
            codex_command=(args.codex_command,),
            sigmap_command=(args.sigmap_command,),
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print(render_doctor(result))
        if args.require_live and not result.live_ready:
            return int(ExitCode.INVALID_INPUT)
        return int(ExitCode.SUCCESS)

    if args.command == "benchmark":
        if args.benchmark_command == "report":
            artifact_dir = Path(args.artifact_dir).resolve()
            json_path = Path(args.json_output or artifact_dir / "report.json").resolve()
            markdown_path = Path(
                args.markdown_output or artifact_dir / "report.md"
            ).resolve()
            try:
                report = write_report(
                    artifact_dir,
                    json_path=json_path,
                    markdown_path=markdown_path,
                )
                payload = {
                    "valid": True,
                    "artifact_count": report["artifact_count"],
                    "json_report": str(json_path),
                    "markdown_report": str(markdown_path),
                }
                exit_code = int(ExitCode.SUCCESS)
            except ReportError as error:
                payload = {"valid": False, "error": str(error)}
                exit_code = int(ExitCode.INVALID_INPUT)
            _print_payload(payload, as_json=args.json)
            return exit_code

        try:
            if args.benchmark_command == "validate":
                task = load_benchmark_task(args.task_file)
                payload = {"valid": True, "task": task.to_dict()}
                exit_code = int(ExitCode.SUCCESS)
            elif args.benchmark_command == "preflight":
                task = load_benchmark_task(args.task_file)
                result = preflight_task(task, worktree_root=args.worktree_root)
                payload = result.to_dict()
                exit_code = (
                    int(ExitCode.SUCCESS)
                    if result.valid
                    else int(ExitCode.INVALID_INPUT)
                )
            else:
                runner = benchmark_runner_factory()
                command_argv = tuple(argv) if argv is not None else tuple(sys.argv[1:])
                artifacts = []
                for task_file in args.task_files:
                    task = load_benchmark_task(task_file)
                    artifacts.extend(
                        runner.run_task(
                            task,
                            task_file=task_file,
                            output_dir=args.output_dir,
                            experiment_id=args.experiment_id,
                            sandbox=args.sandbox,
                            model=args.model,
                            codex_command=(args.codex_command,)
                            if args.codex_command
                            else None,
                            start_condition=args.start_condition,
                            context_timeout_seconds=args.context_timeout,
                            worktree_root=args.worktree_root,
                            exact_command=default_exact_command(command_argv),
                        )
                    )
                payload = {
                    "valid": True,
                    "experiment_id": args.experiment_id,
                    "artifact_count": len(artifacts),
                    "output_dir": str(Path(args.output_dir).resolve()),
                    "passed": sum(artifact.score.passed for artifact in artifacts),
                }
                exit_code = int(ExitCode.SUCCESS)
        except (BenchmarkRunError, BenchmarkValidationError) as error:
            payload = {"valid": False, "error": str(error)}
            exit_code = int(ExitCode.INVALID_INPUT)
        _print_payload(payload, as_json=args.json)
        return exit_code

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
