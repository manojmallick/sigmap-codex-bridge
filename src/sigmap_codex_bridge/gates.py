"""Strict, opt-in regression policies for complete benchmark pairs."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from .paired import ArtifactPair, PairingError, pair_artifacts
from .reporting import ReportError, load_artifacts


GATE_POLICY_SCHEMA_VERSION = 1
GATE_RESULT_SCHEMA_VERSION = 1
RATIO_THRESHOLDS = {
    "max_runtime_ratio": "runtime_seconds",
    "max_input_tokens_ratio": "input_tokens",
    "max_output_tokens_ratio": "output_tokens",
}
THRESHOLD_FIELDS = {
    "require_sigmap_correct_if_raw_correct",
    *RATIO_THRESHOLDS,
    "max_unexpected_files",
    "require_worktree_cleanup",
}


class GateError(ValueError):
    """Raised when a policy or artifact set cannot be evaluated safely."""


@dataclass(frozen=True)
class GatePolicy:
    policy_id: str
    thresholds: Mapping[str, object]


def _strict(value: object, field: str, required: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GateError(f"{field} must be an object")
    fields = set(value)
    missing = sorted(required - fields)
    unknown = sorted(fields - required)
    if missing:
        raise GateError(f"{field} missing fields: {', '.join(missing)}")
    if unknown:
        raise GateError(f"{field} unknown fields: {', '.join(unknown)}")
    return value


def load_gate_policy(path: str | Path) -> GatePolicy:
    """Load a strict YAML/JSON policy with at least one declared threshold."""

    policy_path = Path(path).resolve()
    try:
        raw = policy_path.read_text(encoding="utf-8")
        if policy_path.suffix.lower() == ".json":
            value = json.loads(raw)
        elif policy_path.suffix.lower() in {".yaml", ".yml"}:
            value = yaml.safe_load(raw)
        else:
            raise GateError("gate policy must use .json, .yaml, or .yml")
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as error:
        raise GateError(f"cannot read gate policy: {error}") from error
    value = _strict(value, "policy", {"schema_version", "policy_id", "thresholds"})
    version = value["schema_version"]
    if version != GATE_POLICY_SCHEMA_VERSION or isinstance(version, bool):
        raise GateError("unsupported gate policy schema_version")
    policy_id = value["policy_id"]
    if not isinstance(policy_id, str) or not policy_id.strip():
        raise GateError("policy_id must be a non-empty string")
    thresholds = value["thresholds"]
    if not isinstance(thresholds, Mapping) or not thresholds:
        raise GateError("thresholds must be a non-empty object")
    unknown = sorted(set(thresholds) - THRESHOLD_FIELDS)
    if unknown:
        raise GateError(f"thresholds unknown fields: {', '.join(unknown)}")
    normalized: dict[str, object] = {}
    for field, threshold in thresholds.items():
        if field in {
            "require_sigmap_correct_if_raw_correct",
            "require_worktree_cleanup",
        }:
            if threshold is not True:
                raise GateError(f"thresholds.{field} must be true when declared")
            normalized[field] = True
        elif field == "max_unexpected_files":
            if (
                not isinstance(threshold, int)
                or isinstance(threshold, bool)
                or threshold < 0
            ):
                raise GateError("thresholds.max_unexpected_files must be an integer >= 0")
            normalized[field] = threshold
        else:
            if (
                isinstance(threshold, bool)
                or not isinstance(threshold, (int, float))
                or not math.isfinite(float(threshold))
                or float(threshold) <= 0
            ):
                raise GateError(f"thresholds.{field} must be a finite number > 0")
            normalized[field] = float(threshold)
    return GatePolicy(policy_id.strip(), normalized)


def _score(pair_row: Mapping[str, object], field: str) -> object | None:
    score = pair_row.get("score")
    return score.get(field) if isinstance(score, Mapping) else None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _worktree_cleaned(row: Mapping[str, object]) -> object | None:
    direct = row.get("worktree_cleaned")
    if isinstance(direct, bool):
        return direct
    bridge = row.get("bridge")
    return bridge.get("worktree_cleaned") if isinstance(bridge, Mapping) else None


def _check(
    pair: ArtifactPair,
    *,
    metric: str,
    baseline: object,
    observed: object,
    threshold: object,
    comparison_value: object,
    passed: bool,
    evaluable: bool = True,
    detail: str,
) -> dict[str, object]:
    return {
        **pair.identity(),
        "metric": metric,
        "baseline": baseline,
        "observed": observed,
        "threshold": threshold,
        "comparison_value": comparison_value,
        "evaluable": evaluable,
        "passed": passed,
        "detail": detail,
    }


def evaluate_gate(
    policy: GatePolicy, artifacts: tuple[Mapping[str, object], ...]
) -> dict[str, object]:
    """Evaluate only declared thresholds against complete raw/SigMap pairs."""

    try:
        pairs = pair_artifacts(artifacts)
    except PairingError as error:
        raise GateError(str(error)) from error
    incomplete = [pair for pair in pairs if not pair.complete]
    if incomplete:
        raise GateError(f"cannot evaluate {len(incomplete)} incomplete pair(s)")

    checks: list[dict[str, object]] = []
    for pair in pairs:
        assert pair.raw is not None and pair.sigmap is not None
        raw_passed = _score(pair.raw, "passed")
        sigmap_passed = _score(pair.sigmap, "passed")
        if "require_sigmap_correct_if_raw_correct" in policy.thresholds:
            evaluable = isinstance(raw_passed, bool) and isinstance(sigmap_passed, bool)
            passed = bool(evaluable and (not raw_passed or sigmap_passed))
            checks.append(
                _check(
                    pair,
                    metric="passed",
                    baseline=raw_passed,
                    observed=sigmap_passed,
                    threshold=True,
                    comparison_value=passed if evaluable else None,
                    evaluable=evaluable,
                    passed=passed,
                    detail="SigMap must pass whenever the paired raw baseline passes",
                )
            )
        for threshold_name, metric in RATIO_THRESHOLDS.items():
            if threshold_name not in policy.thresholds:
                continue
            threshold = float(policy.thresholds[threshold_name])
            raw_value = _number(_score(pair.raw, metric))
            sigmap_value = _number(_score(pair.sigmap, metric))
            evaluable = raw_value is not None and raw_value > 0 and sigmap_value is not None
            ratio = sigmap_value / raw_value if evaluable else None
            checks.append(
                _check(
                    pair,
                    metric=metric,
                    baseline=raw_value,
                    observed=sigmap_value,
                    threshold=threshold,
                    comparison_value=ratio,
                    evaluable=evaluable,
                    passed=bool(evaluable and ratio is not None and ratio <= threshold),
                    detail=(
                        f"SigMap/raw ratio must be <= {threshold}"
                        if evaluable
                        else "ratio unavailable because a metric is missing or raw is zero"
                    ),
                )
            )
        if "max_unexpected_files" in policy.thresholds:
            threshold = int(policy.thresholds["max_unexpected_files"])
            raw_files = _score(pair.raw, "unexpected_files")
            sigmap_files = _score(pair.sigmap, "unexpected_files")
            raw_count = len(raw_files) if isinstance(raw_files, list) else None
            sigmap_count = len(sigmap_files) if isinstance(sigmap_files, list) else None
            evaluable = raw_count is not None and sigmap_count is not None
            checks.append(
                _check(
                    pair,
                    metric="unexpected_files",
                    baseline=raw_count,
                    observed=sigmap_count,
                    threshold=threshold,
                    comparison_value=sigmap_count,
                    evaluable=evaluable,
                    passed=bool(evaluable and sigmap_count is not None and sigmap_count <= threshold),
                    detail=f"SigMap unexpected-file count must be <= {threshold}",
                )
            )
        if "require_worktree_cleanup" in policy.thresholds:
            raw_cleaned = _worktree_cleaned(pair.raw)
            sigmap_cleaned = _worktree_cleaned(pair.sigmap)
            evaluable = isinstance(raw_cleaned, bool) and isinstance(sigmap_cleaned, bool)
            checks.append(
                _check(
                    pair,
                    metric="worktree_cleaned",
                    baseline=raw_cleaned,
                    observed=sigmap_cleaned,
                    threshold=True,
                    comparison_value=bool(raw_cleaned and sigmap_cleaned),
                    evaluable=evaluable,
                    passed=bool(evaluable and raw_cleaned and sigmap_cleaned),
                    detail="both raw and SigMap worktrees must be cleaned",
                )
            )

    failures = [check for check in checks if not check["passed"]]
    return {
        "gate_result_schema_version": GATE_RESULT_SCHEMA_VERSION,
        "policy_id": policy.policy_id,
        "thresholds": dict(policy.thresholds),
        "passed": not failures,
        "pair_count": len(pairs),
        "check_count": len(checks),
        "failure_count": len(failures),
        "checks": checks,
    }


def evaluate_gate_directory(
    policy_path: str | Path, artifact_dir: str | Path
) -> dict[str, object]:
    policy = load_gate_policy(policy_path)
    try:
        artifacts = load_artifacts(artifact_dir)
    except ReportError as error:
        raise GateError(str(error)) from error
    return evaluate_gate(policy, artifacts)


def write_gate_result(path: str | Path, result: Mapping[str, object]) -> None:
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)
