"""Deterministic pairing and within-pair benchmark analysis."""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping


MIN_CONFIDENCE_PAIRS = 10
BOOTSTRAP_RESAMPLES = 10_000
PAIRED_METRICS = ("runtime_seconds", "input_tokens", "output_tokens")


class PairingError(ValueError):
    """Raised when retained artifacts cannot be paired unambiguously."""


@dataclass(frozen=True)
class ArtifactPair:
    experiment_id: str
    task_id: str
    repetition: int
    pair_id: str
    raw: Mapping[str, object] | None
    sigmap: Mapping[str, object] | None

    @property
    def complete(self) -> bool:
        return self.raw is not None and self.sigmap is not None

    def identity(self) -> dict[str, object]:
        return {
            "experiment_id": self.experiment_id,
            "task_id": self.task_id,
            "repetition": self.repetition,
            "pair_id": self.pair_id,
        }


def pair_artifacts(artifacts: Iterable[Mapping[str, object]]) -> tuple[ArtifactPair, ...]:
    """Group artifacts by their declared pair and reject duplicate conditions."""

    grouped: dict[
        tuple[str, str, int, str], dict[str, Mapping[str, object]]
    ] = defaultdict(dict)
    for row in artifacts:
        try:
            task_id = str(row["task_id"])
            repetition = int(row["repetition"])
            pair_id = str(row.get("pair_id") or f"{task_id}-r{repetition:03d}")
            key = (
                str(row["experiment_id"]),
                task_id,
                repetition,
                pair_id,
            )
            condition = str(row["condition"])
        except (KeyError, TypeError, ValueError) as error:
            raise PairingError("artifact has invalid pair identity fields") from error
        if not all((key[0], key[1], key[3])) or key[2] < 1:
            raise PairingError("artifact has empty or invalid pair identity fields")
        if condition not in {"raw", "sigmap"}:
            raise PairingError(f"unsupported paired condition: {condition}")
        if condition in grouped[key]:
            raise PairingError(
                f"duplicate {condition} artifact for {key[1]} {key[3]}"
            )
        grouped[key][condition] = row

    return tuple(
        ArtifactPair(
            experiment_id=key[0],
            task_id=key[1],
            repetition=key[2],
            pair_id=key[3],
            raw=conditions.get("raw"),
            sigmap=conditions.get("sigmap"),
        )
        for key, conditions in sorted(grouped.items())
    )


def _score_value(row: Mapping[str, object] | None, metric: str) -> float | None:
    if row is None:
        return None
    score = row.get("score")
    if not isinstance(score, Mapping):
        return None
    value = score.get(metric)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _passed(row: Mapping[str, object]) -> bool:
    score = row.get("score")
    return score.get("passed") is True if isinstance(score, Mapping) else False


def _percentile(sorted_values: list[float], probability: float) -> float:
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _confidence_interval(values: list[float], metric: str) -> dict[str, object]:
    if len(values) < MIN_CONFIDENCE_PAIRS:
        return {
            "status": "insufficient_evidence",
            "observed_pairs": len(values),
            "required_pairs": MIN_CONFIDENCE_PAIRS,
            "reason": "paired confidence intervals require at least 10 values",
        }
    generator = random.Random(f"sigmap-paired-bootstrap-v1:{metric}")
    medians = sorted(
        float(statistics.median(generator.choices(values, k=len(values))))
        for _ in range(BOOTSTRAP_RESAMPLES)
    )
    return {
        "status": "available",
        "method": "deterministic paired bootstrap percentile",
        "confidence_level": 0.95,
        "resamples": BOOTSTRAP_RESAMPLES,
        "lower": _percentile(medians, 0.025),
        "upper": _percentile(medians, 0.975),
    }


def _metric_analysis(pairs: tuple[ArtifactPair, ...], metric: str) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    deltas: list[float] = []
    relative_deltas: list[float] = []
    directions = {"improved": 0, "unchanged": 0, "regressed": 0, "unavailable": 0}
    for pair in pairs:
        raw = _score_value(pair.raw, metric)
        sigmap = _score_value(pair.sigmap, metric)
        delta = sigmap - raw if raw is not None and sigmap is not None else None
        relative = delta / raw if delta is not None and raw else None
        if delta is None:
            direction = "unavailable"
        elif delta < 0:
            direction = "improved"
        elif delta > 0:
            direction = "regressed"
        else:
            direction = "unchanged"
        directions[direction] += 1
        row = {
            **pair.identity(),
            "raw": raw,
            "sigmap": sigmap,
            "delta": delta,
            "relative_delta": relative,
            "direction": direction,
        }
        rows.append(row)
        if delta is not None:
            deltas.append(delta)
        if relative is not None:
            relative_deltas.append(relative)

    median_delta = float(statistics.median(deltas)) if deltas else None
    mad = (
        float(statistics.median(abs(value - median_delta) for value in deltas))
        if deltas and median_delta is not None
        else None
    )
    return {
        "comparable_pairs": len(deltas),
        "direction_counts": directions,
        "effect": {
            "median_delta": median_delta,
            "median_relative_delta": (
                float(statistics.median(relative_deltas)) if relative_deltas else None
            ),
            "median_absolute_deviation": mad,
        },
        "confidence_interval": _confidence_interval(deltas, metric),
        "pairs": rows,
    }


def analyze_pairs(artifacts: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """Return complete-pair deltas and honest small-sample uncertainty metadata."""

    pairs = pair_artifacts(artifacts)
    complete = tuple(pair for pair in pairs if pair.complete)
    incomplete = [
        {
            **pair.identity(),
            "conditions_present": [
                condition
                for condition, row in (("raw", pair.raw), ("sigmap", pair.sigmap))
                if row is not None
            ],
        }
        for pair in pairs
        if not pair.complete
    ]
    transitions = {
        "both_passed": 0,
        "raw_only_passed": 0,
        "sigmap_only_passed": 0,
        "both_failed": 0,
    }
    for pair in complete:
        assert pair.raw is not None and pair.sigmap is not None
        raw_passed = _passed(pair.raw)
        sigmap_passed = _passed(pair.sigmap)
        if raw_passed and sigmap_passed:
            transitions["both_passed"] += 1
        elif raw_passed:
            transitions["raw_only_passed"] += 1
        elif sigmap_passed:
            transitions["sigmap_only_passed"] += 1
        else:
            transitions["both_failed"] += 1
    return {
        "pair_count": len(pairs),
        "complete_pair_count": len(complete),
        "minimum_confidence_pairs": MIN_CONFIDENCE_PAIRS,
        "incomplete_pairs": incomplete,
        "correctness_transitions": transitions,
        "metrics": {metric: _metric_analysis(complete, metric) for metric in PAIRED_METRICS},
    }
