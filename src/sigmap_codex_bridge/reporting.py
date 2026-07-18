"""Deterministic reports generated only from retained benchmark artifacts."""

from __future__ import annotations

import json
import os
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping

from .paired import PairingError, analyze_pairs


REPORT_SCHEMA_VERSION = 1
METRICS = (
    "runtime_seconds",
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "patch_lines",
    "tool_events",
    "command_events",
)


class ReportError(ValueError):
    """Raised when artifacts cannot produce a trustworthy report."""


def load_artifacts(path: str | Path) -> tuple[dict[str, object], ...]:
    root = Path(path)
    artifacts: list[dict[str, object]] = []
    for artifact_path in sorted(root.glob("*.json")):
        try:
            value = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ReportError(f"cannot read artifact {artifact_path}: {error}") from error
        if not isinstance(value, dict) or "artifact_schema_version" not in value:
            continue
        if value["artifact_schema_version"] != 1:
            raise ReportError(f"unsupported artifact schema in {artifact_path}")
        artifacts.append(value)
    if not artifacts:
        raise ReportError(f"no benchmark artifacts found in {root}")
    return tuple(artifacts)


def _median(values: Iterable[object]) -> float | None:
    numbers = [float(value) for value in values if isinstance(value, (int, float))]
    return float(statistics.median(numbers)) if numbers else None


def _summary(artifacts: Iterable[Mapping[str, object]]) -> dict[str, object]:
    rows = list(artifacts)
    passed = sum(bool(row["score"]["passed"]) for row in rows)  # type: ignore[index]
    attempts = len(rows)
    medians = {
        metric: _median(row["score"].get(metric) for row in rows)  # type: ignore[union-attr]
        for metric in METRICS
    }
    return {
        "attempts": attempts,
        "passed": passed,
        "failed": attempts - passed,
        "success_rate": passed / attempts if attempts else None,
        "medians": medians,
    }


def _ratio(numerator: object, denominator: object) -> float | None:
    if not isinstance(numerator, (int, float)) or not isinstance(
        denominator, (int, float)
    ):
        return None
    return float(numerator) / float(denominator) if denominator else None


def generate_report(artifacts: Iterable[dict[str, object]]) -> dict[str, object]:
    rows = sorted(
        artifacts,
        key=lambda row: (
            str(row["experiment_id"]),
            str(row["task_id"]),
            int(row["repetition"]),
            int(row["order_position"]),
        ),
    )
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    overall: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        condition = str(row["condition"])
        grouped[(str(row["task_id"]), condition)].append(row)
        overall[condition].append(row)

    tasks: dict[str, dict[str, object]] = {}
    for task_id, _condition in sorted(grouped):
        tasks[task_id] = {
            condition: _summary(grouped.get((task_id, condition), ()))
            for condition in ("raw", "sigmap")
        }

    failures = [
        {
            "experiment_id": row["experiment_id"],
            "task_id": row["task_id"],
            "repetition": row["repetition"],
            "condition": row["condition"],
            "failure_details": row.get("failure_details", []),
        }
        for row in rows
        if row.get("failure_details") or not bool(row["score"]["passed"])  # type: ignore[index]
    ]
    environments = sorted(
        {
            json.dumps(row["environment"], sort_keys=True, separators=(",", ":"))
            for row in rows
        }
    )
    commands = sorted({tuple(row.get("exact_command", [])) for row in rows})
    overall_summary = {
        condition: _summary(overall.get(condition, ()))
        for condition in ("raw", "sigmap")
    }
    raw = overall_summary["raw"]
    sigmap = overall_summary["sigmap"]
    raw_medians = raw["medians"]
    sigmap_medians = sigmap["medians"]
    assert isinstance(raw_medians, Mapping)
    assert isinstance(sigmap_medians, Mapping)
    comparisons = {
        "sigmap_to_raw_success_rate_ratio": _ratio(
            sigmap["success_rate"], raw["success_rate"]
        ),
        "sigmap_to_raw_median_runtime_ratio": _ratio(
            sigmap_medians["runtime_seconds"], raw_medians["runtime_seconds"]
        ),
        "sigmap_to_raw_median_input_tokens_ratio": _ratio(
            sigmap_medians["input_tokens"], raw_medians["input_tokens"]
        ),
    }
    try:
        paired_analysis = analyze_pairs(rows)
    except PairingError as error:
        raise ReportError(str(error)) from error
    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "artifact_count": len(rows),
        "experiment_ids": sorted({str(row["experiment_id"]) for row in rows}),
        "exact_commands": [list(command) for command in commands],
        "environments": [json.loads(value) for value in environments],
        "overall": overall_summary,
        "comparisons": comparisons,
        "paired_analysis": paired_analysis,
        "tasks": tasks,
        "failures": failures,
    }


def render_markdown(report: Mapping[str, object]) -> str:
    lines = [
        "# Paired raw versus SigMap benchmark report",
        "",
        f"Artifacts: {report['artifact_count']}",
        "",
        "## Overall",
        "",
        "| Condition | Passed / attempts | Success rate | Median runtime (s) | Median input tokens | Median patch lines |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    overall = report["overall"]
    assert isinstance(overall, Mapping)
    for condition in ("raw", "sigmap"):
        summary = overall[condition]
        assert isinstance(summary, Mapping)
        medians = summary["medians"]
        assert isinstance(medians, Mapping)
        rate = summary["success_rate"]
        rate_text = "n/a" if rate is None else f"{float(rate):.1%}"
        lines.append(
            f"| {condition} | {summary['passed']} / {summary['attempts']} | {rate_text} | "
            f"{_format_number(medians['runtime_seconds'])} | "
            f"{_format_number(medians['input_tokens'])} | "
            f"{_format_number(medians['patch_lines'])} |"
        )

    paired = report.get("paired_analysis")
    if isinstance(paired, Mapping):
        lines.extend(("", "## Paired analysis", ""))
        lines.append(
            f"Complete pairs: {paired['complete_pair_count']} / {paired['pair_count']}. "
            f"Confidence intervals require {paired['minimum_confidence_pairs']} "
            "comparable pairs."
        )
        lines.extend(
            (
                "",
                "| Metric | Comparable pairs | Improved / unchanged / regressed | Median delta | 95% interval |",
                "|---|---:|---:|---:|---:|",
            )
        )
        metrics = paired["metrics"]
        assert isinstance(metrics, Mapping)
        for metric in ("runtime_seconds", "input_tokens", "output_tokens"):
            analysis = metrics[metric]
            assert isinstance(analysis, Mapping)
            directions = analysis["direction_counts"]
            effect = analysis["effect"]
            interval = analysis["confidence_interval"]
            assert isinstance(directions, Mapping)
            assert isinstance(effect, Mapping)
            assert isinstance(interval, Mapping)
            if interval["status"] == "available":
                interval_text = (
                    f"{_format_number(interval['lower'])} to "
                    f"{_format_number(interval['upper'])}"
                )
            else:
                interval_text = "insufficient evidence"
            lines.append(
                f"| {metric} | {analysis['comparable_pairs']} | "
                f"{directions['improved']} / {directions['unchanged']} / "
                f"{directions['regressed']} | "
                f"{_format_number(effect['median_delta'])} | {interval_text} |"
            )

    lines.extend(("", "## Per task", ""))
    tasks = report["tasks"]
    assert isinstance(tasks, Mapping)
    for task_id, conditions in tasks.items():
        assert isinstance(conditions, Mapping)
        lines.extend((f"### {task_id}", "", "| Condition | Passed / attempts | Success rate | Median runtime (s) | Median output tokens |", "|---|---:|---:|---:|---:|"))
        for condition in ("raw", "sigmap"):
            summary = conditions[condition]
            assert isinstance(summary, Mapping)
            medians = summary["medians"]
            assert isinstance(medians, Mapping)
            rate = summary["success_rate"]
            rate_text = "n/a" if rate is None else f"{float(rate):.1%}"
            lines.append(
                f"| {condition} | {summary['passed']} / {summary['attempts']} | "
                f"{rate_text} | {_format_number(medians['runtime_seconds'])} | "
                f"{_format_number(medians['output_tokens'])} |"
            )
        lines.append("")

    failures = report["failures"]
    assert isinstance(failures, list)
    lines.extend(("## Failed runs", ""))
    if failures:
        for failure in failures:
            lines.append(
                f"- {failure['task_id']} repetition {failure['repetition']} "
                f"({failure['condition']}): "
                f"{'; '.join(failure['failure_details']) or 'correctness check failed'}"
            )
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)


def _format_number(value: object) -> str:
    if value is None:
        return "n/a"
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.3f}"


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def write_report(
    artifact_dir: str | Path,
    *,
    json_path: str | Path,
    markdown_path: str | Path,
) -> dict[str, object]:
    report = generate_report(load_artifacts(artifact_dir))
    json_output = Path(json_path)
    markdown_output = Path(markdown_path)
    _atomic_text(json_output, json.dumps(report, indent=2, sort_keys=True) + "\n")
    _atomic_text(markdown_output, render_markdown(report))
    return report
