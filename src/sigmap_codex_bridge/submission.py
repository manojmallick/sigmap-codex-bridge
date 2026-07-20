"""Integrity and readiness checks for Build Week submission metadata."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from . import __version__


@dataclass(frozen=True)
class SubmissionCheck:
    name: str
    status: str
    detail: str
    fix: str | None = None
    required_for_integrity: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SubmissionResult:
    valid: bool
    submission_ready: bool
    checks: tuple[SubmissionCheck, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "submission_ready": self.submission_ready,
            "checks": [check.to_dict() for check in self.checks],
        }


def _nested(value: Mapping[str, Any], *path: str) -> object | None:
    current: object = value
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _external_value(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    lowered = value.strip().lower()
    return not any(marker in lowered for marker in ("placeholder", "todo", "tbd"))


def _https_url(value: object) -> bool:
    if not _external_value(value):
        return False
    parsed = urlparse(str(value))
    return parsed.scheme == "https" and bool(parsed.netloc)


def _release_version(value: object) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", value)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _codex_evidence(
    payload: Mapping[str, Any], repository_root: Path
) -> tuple[bool, str]:
    """Validate inspectable Codex/GPT provenance without trusting prose alone."""

    evidence = _nested(payload, "evidence", "codex")
    if not isinstance(evidence, Mapping):
        return False, "missing evidence.codex object"

    session_id = evidence.get("feedback_session_id")
    external_session_id = _nested(payload, "external", "feedback_session_id")
    session_ok = (
        isinstance(session_id, str)
        and re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            session_id,
            re.IGNORECASE,
        )
        is not None
        and session_id == external_session_id
    )
    model_ok = str(evidence.get("model", "")).strip().lower() == "gpt-5.6"
    contribution = evidence.get("contribution")
    contribution_ok = isinstance(contribution, str) and len(contribution.strip()) >= 20
    command = evidence.get("verification_command")
    command_ok = (
        isinstance(command, list)
        and bool(command)
        and all(isinstance(item, str) and item.strip() for item in command)
    )

    changed_files = evidence.get("changed_files")
    files_ok = isinstance(changed_files, list) and bool(changed_files)
    if files_ok:
        for value in changed_files:
            if not isinstance(value, str) or not value or Path(value).is_absolute():
                files_ok = False
                break
            candidate = (repository_root / value).resolve()
            try:
                candidate.relative_to(repository_root)
            except ValueError:
                files_ok = False
                break
            if not candidate.is_file():
                files_ok = False
                break

    states = {
        "session": session_ok,
        "model": model_ok,
        "contribution": contribution_ok,
        "verification_command": command_ok,
        "changed_files": files_ok,
    }
    failed = [name for name, ok in states.items() if not ok]
    if failed:
        return False, f"invalid fields: {', '.join(failed)}"
    return True, f"GPT-5.6 session {session_id}; {len(changed_files)} changed files"


def validate_submission(path: str | Path) -> SubmissionResult:
    """Validate evidence consistency and report separate external blockers."""

    metadata_path = Path(path).resolve()
    checks: list[SubmissionCheck] = []
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        check = SubmissionCheck(
            "metadata",
            "fail",
            f"cannot load submission metadata: {error}",
            "Pass a readable Build Week submission JSON file.",
        )
        return SubmissionResult(False, False, (check,))
    if not isinstance(payload, dict):
        check = SubmissionCheck("metadata", "fail", "metadata must be a JSON object")
        return SubmissionResult(False, False, (check,))

    schema_ok = payload.get("schema_version") == 1
    checks.append(
        SubmissionCheck(
            "schema_version",
            "ok" if schema_ok else "fail",
            f"schema version {payload.get('schema_version')!r}",
            None if schema_ok else "Use schema_version 1.",
        )
    )
    version = _nested(payload, "release", "version")
    metadata_version = _release_version(version)
    package_version = _release_version(__version__)
    version_ok = (
        metadata_version is not None
        and package_version is not None
        and metadata_version <= package_version
    )
    checks.append(
        SubmissionCheck(
            "package_version",
            "ok" if version_ok else "fail",
            f"metadata {version!r}; package {__version__!r}",
            (
                None
                if version_ok
                else "Use a semantic release version no newer than the installed package."
            ),
        )
    )

    repository_root = metadata_path.parent.parent
    codex_ok, codex_detail = _codex_evidence(payload, repository_root)
    checks.append(
        SubmissionCheck(
            "codex_evidence",
            "ok" if codex_ok else "fail",
            codex_detail,
            (
                None
                if codex_ok
                else "Add matching GPT-5.6 session, contribution, command array, and repository-local changed files."
            ),
        )
    )
    report_value = _nested(payload, "evidence", "report_path")
    report_path: Path | None = None
    if isinstance(report_value, str) and report_value and not Path(report_value).is_absolute():
        candidate = (repository_root / report_value).resolve()
        try:
            candidate.relative_to(repository_root)
            report_path = candidate
        except ValueError:
            report_path = None
    path_ok = report_path is not None and report_path.is_file()
    checks.append(
        SubmissionCheck(
            "report_path",
            "ok" if path_ok else "fail",
            str(report_value),
            None if path_ok else "Use an existing report path inside the repository.",
        )
    )

    report: dict[str, Any] | None = None
    if path_ok and report_path is not None:
        report_bytes = report_path.read_bytes()
        actual_hash = hashlib.sha256(report_bytes).hexdigest()
        expected_hash = _nested(payload, "evidence", "report_sha256")
        hash_ok = actual_hash == expected_hash
        checks.append(
            SubmissionCheck(
                "report_sha256",
                "ok" if hash_ok else "fail",
                actual_hash,
                None if hash_ok else "Update metadata only from the frozen report bytes.",
            )
        )
        try:
            loaded = json.loads(report_bytes)
            report = loaded if isinstance(loaded, dict) else None
        except json.JSONDecodeError:
            report = None
        checks.append(
            SubmissionCheck(
                "report_json",
                "ok" if report is not None else "fail",
                "report is a JSON object" if report is not None else "invalid report JSON",
            )
        )

    result_fields = {
        "artifact_count": ("artifact_count",),
        "raw_passed": ("overall", "raw", "passed"),
        "sigmap_passed": ("overall", "sigmap", "passed"),
        "raw_median_runtime_seconds": (
            "overall",
            "raw",
            "medians",
            "runtime_seconds",
        ),
        "sigmap_median_runtime_seconds": (
            "overall",
            "sigmap",
            "medians",
            "runtime_seconds",
        ),
        "raw_median_input_tokens": (
            "overall",
            "raw",
            "medians",
            "input_tokens",
        ),
        "sigmap_median_input_tokens": (
            "overall",
            "sigmap",
            "medians",
            "input_tokens",
        ),
    }
    results_ok = report is not None
    mismatches: list[str] = []
    for metadata_key, report_path_parts in result_fields.items():
        declared = _nested(payload, "evidence", "measured_results", metadata_key)
        measured = _nested(report, *report_path_parts) if report is not None else None
        if declared != measured:
            results_ok = False
            mismatches.append(metadata_key)
    checks.append(
        SubmissionCheck(
            "measured_results",
            "ok" if results_ok else "fail",
            "metadata matches the frozen report"
            if results_ok
            else f"mismatched fields: {', '.join(mismatches) or 'report unavailable'}",
            None if results_ok else "Copy numbers directly from the frozen JSON report.",
        )
    )
    experiment_id = _nested(payload, "evidence", "experiment_id")
    report_experiments = report.get("experiment_ids", []) if report is not None else []
    experiment_ok = (
        isinstance(experiment_id, str)
        and isinstance(report_experiments, list)
        and experiment_id in report_experiments
    )
    checks.append(
        SubmissionCheck(
            "experiment_id",
            "ok" if experiment_ok else "fail",
            str(experiment_id),
            None if experiment_ok else "Use an experiment ID present in the frozen report.",
        )
    )

    external = {
        "feedback_session_id": _external_value(
            _nested(payload, "external", "feedback_session_id")
        ),
        "video_url": _https_url(_nested(payload, "external", "video_url")),
        "devpost_url": _https_url(_nested(payload, "external", "devpost_url")),
    }
    for name, present in external.items():
        checks.append(
            SubmissionCheck(
                name,
                "ok" if present else "warn",
                "provided" if present else "missing external submission value",
                None if present else f"Add the real {name.replace('_', ' ')}.",
                required_for_integrity=False,
            )
        )

    missing_external = [name for name, present in external.items() if not present]
    expected_status = "ready" if not missing_external else "blocked"
    declared_status = _nested(payload, "release", "status")
    status_ok = declared_status == expected_status
    checks.append(
        SubmissionCheck(
            "release_status",
            "ok" if status_ok else "fail",
            f"declared {declared_status!r}; expected {expected_status!r}",
            None if status_ok else "Mark incomplete metadata blocked; mark it ready only when complete.",
        )
    )

    valid = all(
        check.status == "ok" for check in checks if check.required_for_integrity
    )
    return SubmissionResult(
        valid=valid,
        submission_ready=valid and not missing_external,
        checks=tuple(checks),
    )


def render_submission(result: SubmissionResult) -> str:
    lines = [
        f"Metadata integrity: {'VALID' if result.valid else 'INVALID'}",
        f"Build Week submission: {'READY' if result.submission_ready else 'BLOCKED'}",
        "",
    ]
    icons = {"ok": "✓", "warn": "!", "fail": "✗"}
    for check in result.checks:
        lines.append(f"{icons.get(check.status, '?')} {check.name}: {check.detail}")
        if check.fix:
            lines.append(f"  Fix: {check.fix}")
    return "\n".join(lines)
