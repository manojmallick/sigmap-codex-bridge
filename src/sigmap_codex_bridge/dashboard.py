"""Reproducible aggregate views generated from validated retained artifacts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Mapping, Sequence

from .reporting import ReportError, generate_report, load_artifacts


DASHBOARD_SCHEMA_VERSION = 1
NON_CLAIM = (
    "This dashboard summarizes retained compatible evidence; it does not establish "
    "general model quality, statistical significance, or independent replication."
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _compatibility_fields(artifacts: Sequence[Mapping[str, object]]) -> dict[str, object]:
    task_ids = sorted({str(row.get("task_id")) for row in artifacts})
    environments = sorted(
        {
            json.dumps(row.get("environment", {}), separators=(",", ":"), sort_keys=True)
            for row in artifacts
        }
    )
    packs = sorted(
        {
            json.dumps(row.get("benchmark_pack"), separators=(",", ":"), sort_keys=True)
            for row in artifacts
            if row.get("benchmark_pack") is not None
        }
    )
    return {
        "task_ids": task_ids,
        "environments": [json.loads(value) for value in environments],
        "benchmark_packs": [json.loads(value) for value in packs],
    }


def generate_dashboard(artifact_dirs: Sequence[str | Path]) -> dict[str, object]:
    """Generate stable dashboard entries without combining incompatible strata."""

    if not artifact_dirs:
        raise ReportError("at least one artifact directory is required")
    entries: list[dict[str, object]] = []
    for index, artifact_dir in enumerate(artifact_dirs):
        artifacts = load_artifacts(artifact_dir)
        report = generate_report(artifacts)
        compatibility = _compatibility_fields(artifacts)
        compatibility_key = hashlib.sha256(_canonical(compatibility)).hexdigest()
        report_hash = hashlib.sha256(_canonical(report)).hexdigest()
        paired = report["paired_analysis"]
        assert isinstance(paired, Mapping)
        entries.append(
            {
                "source_index": index,
                "source_label": Path(artifact_dir).name,
                "compatibility_key": compatibility_key,
                "compatibility": compatibility,
                "report_sha256": report_hash,
                "artifact_count": report["artifact_count"],
                "complete_pair_count": paired["complete_pair_count"],
                "excluded_incomplete_attempt_count": paired[
                    "excluded_incomplete_attempt_count"
                ],
                "failure_count": len(report["failures"]),
                "report": report,
            }
        )
    return {
        "dashboard_schema_version": DASHBOARD_SCHEMA_VERSION,
        "verified_artifact_inputs": True,
        "entry_count": len(entries),
        "non_claim": NON_CLAIM,
        "entries": entries,
    }


def render_dashboard(dashboard: Mapping[str, object]) -> str:
    lines = [
        "# SigMap Codex Bridge evidence dashboard",
        "",
        str(dashboard["non_claim"]),
        "",
        "| Source | Compatibility stratum | Artifacts | Complete pairs | Incomplete attempts | Failures |",
        "|---|---|---:|---:|---:|---:|",
    ]
    entries = dashboard["entries"]
    assert isinstance(entries, list)
    for entry in entries:
        assert isinstance(entry, Mapping)
        lines.append(
            f"| {entry['source_label']} | `{str(entry['compatibility_key'])[:12]}` | "
            f"{entry['artifact_count']} | {entry['complete_pair_count']} | "
            f"{entry['excluded_incomplete_attempt_count']} | {entry['failure_count']} |"
        )
    lines.extend(
        (
            "",
            "Compatibility strata are intentionally not merged. Full per-task values, "
            "negative results, failures, and uncertainty remain in each embedded report.",
            "",
        )
    )
    return "\n".join(lines)


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def write_dashboard(
    artifact_dirs: Sequence[str | Path],
    *,
    json_path: str | Path,
    markdown_path: str | Path,
) -> dict[str, object]:
    dashboard = generate_dashboard(artifact_dirs)
    _atomic_text(
        Path(json_path), json.dumps(dashboard, indent=2, sort_keys=True) + "\n"
    )
    _atomic_text(Path(markdown_path), render_dashboard(dashboard))
    return dashboard
