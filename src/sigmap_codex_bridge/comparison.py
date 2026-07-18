"""Compatibility-aware comparison of retained benchmark experiments."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping

from .paired import PairingError, analyze_pairs
from .reporting import ReportError, load_artifacts


COMPARISON_SCHEMA_VERSION = 1


class ComparisonError(ValueError):
    """Raised when experiments cannot be compared honestly."""


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _stratum(row: Mapping[str, object]) -> dict[str, object]:
    environment = _mapping(row.get("environment"))
    pack = _mapping(row.get("benchmark_pack"))
    command = environment.get("codex_command")
    if isinstance(command, list):
        codex_command: object = [str(part) for part in command]
    else:
        codex_command = None
    return {
        "task_id": str(row.get("task_id", "")),
        "model": environment.get("model"),
        "codex_command": codex_command,
        "platform": environment.get("platform"),
        "pack_id": pack.get("pack_id"),
        "pack_schema_version": pack.get("pack_schema_version"),
        "pack_manifest_sha256": pack.get("manifest_sha256"),
    }


def _group(
    rows: Iterable[Mapping[str, object]],
) -> dict[str, tuple[dict[str, object], list[Mapping[str, object]]]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    strata: dict[str, dict[str, object]] = {}
    for row in rows:
        stratum = _stratum(row)
        key = json.dumps(stratum, sort_keys=True, separators=(",", ":"))
        strata[key] = stratum
        grouped[key].append(row)
    return {key: (strata[key], grouped[key]) for key in sorted(grouped)}


def _dataset(rows: Iterable[Mapping[str, object]]) -> dict[str, object]:
    values = list(rows)
    return {
        "artifact_count": len(values),
        "experiment_ids": sorted({str(row.get("experiment_id", "")) for row in values}),
        "resolved_revisions": sorted(
            {str(row.get("resolved_revision", "")) for row in values}
        ),
    }


def compare_artifacts(
    baseline: Iterable[Mapping[str, object]],
    candidate: Iterable[Mapping[str, object]],
    *,
    allow_incompatible: bool = False,
) -> dict[str, object]:
    """Compare only like-for-like strata unless an override is recorded."""

    baseline_rows = list(baseline)
    candidate_rows = list(candidate)
    baseline_groups = _group(baseline_rows)
    candidate_groups = _group(candidate_rows)
    baseline_keys = set(baseline_groups)
    candidate_keys = set(candidate_groups)
    mismatches = [
        {"side": "baseline_only", "stratum": baseline_groups[key][0]}
        for key in sorted(baseline_keys - candidate_keys)
    ] + [
        {"side": "candidate_only", "stratum": candidate_groups[key][0]}
        for key in sorted(candidate_keys - baseline_keys)
    ]
    compatible = not mismatches
    if not compatible and not allow_incompatible:
        raise ComparisonError(
            "experiment strata differ; rerun like-for-like or pass --allow-incompatible"
        )

    strata = []
    try:
        for key in sorted(baseline_keys & candidate_keys):
            stratum, baseline_group = baseline_groups[key]
            _candidate_stratum, candidate_group = candidate_groups[key]
            baseline_analysis = analyze_pairs(baseline_group)
            candidate_analysis = analyze_pairs(candidate_group)
            effect_changes: dict[str, float | None] = {}
            for metric in ("runtime_seconds", "input_tokens", "output_tokens"):
                baseline_effect = baseline_analysis["metrics"][metric]["effect"][  # type: ignore[index]
                    "median_delta"
                ]
                candidate_effect = candidate_analysis["metrics"][metric]["effect"][  # type: ignore[index]
                    "median_delta"
                ]
                effect_changes[metric] = (
                    float(candidate_effect) - float(baseline_effect)
                    if isinstance(baseline_effect, (int, float))
                    and isinstance(candidate_effect, (int, float))
                    else None
                )
            strata.append(
                {
                    "stratum": stratum,
                    "baseline_paired_analysis": baseline_analysis,
                    "candidate_paired_analysis": candidate_analysis,
                    "candidate_minus_baseline_median_delta": effect_changes,
                }
            )
    except PairingError as error:
        raise ComparisonError(str(error)) from error

    return {
        "comparison_schema_version": COMPARISON_SCHEMA_VERSION,
        "compatible": compatible,
        "compatibility_override": bool(allow_incompatible and not compatible),
        "mismatches": mismatches,
        "baseline": _dataset(baseline_rows),
        "candidate": _dataset(candidate_rows),
        "strata": strata,
    }


def compare_directories(
    baseline_dir: str | Path,
    candidate_dir: str | Path,
    *,
    allow_incompatible: bool = False,
) -> dict[str, object]:
    try:
        baseline = load_artifacts(baseline_dir)
        candidate = load_artifacts(candidate_dir)
    except ReportError as error:
        raise ComparisonError(str(error)) from error
    return compare_artifacts(
        baseline,
        candidate,
        allow_incompatible=allow_incompatible,
    )


def write_comparison(path: str | Path, comparison: Mapping[str, object]) -> None:
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(comparison, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)
