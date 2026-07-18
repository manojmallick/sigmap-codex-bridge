import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from sigmap_codex_bridge.cli import main
from sigmap_codex_bridge.comparison import (
    ComparisonError,
    compare_artifacts,
    write_comparison,
)
from sigmap_codex_bridge.gates import (
    GateError,
    evaluate_gate,
    load_gate_policy,
)
from sigmap_codex_bridge.paired import PairingError, analyze_pairs


def artifact(
    condition: str,
    repetition: int,
    *,
    experiment: str = "fixture",
    revision: str = "a" * 40,
    task: str = "task",
    model: str = "fixture-model",
    runtime: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    passed: bool = True,
    unexpected_files: list[str] | None = None,
    cleaned: bool = True,
) -> dict[str, object]:
    score: dict[str, object] = {
        "passed": passed,
        "runtime_seconds": (
            runtime if runtime is not None else (2.0 if condition == "raw" else 1.0)
        ),
        "input_tokens": (
            input_tokens
            if input_tokens is not None
            else (20 if condition == "raw" else 10)
        ),
        "output_tokens": (
            output_tokens
            if output_tokens is not None
            else (8 if condition == "raw" else 4)
        ),
        "unexpected_files": unexpected_files or [],
    }
    return {
        "artifact_schema_version": 1,
        "experiment_id": experiment,
        "task_id": task,
        "task_file": f"{task}.yaml",
        "resolved_revision": revision,
        "repetition": repetition,
        "pair_id": f"{task}-r{repetition:03d}",
        "condition": condition,
        "order_position": 1 if condition == "raw" else 2,
        "exact_command": ["sigmap-bridge", "benchmark", "run"],
        "environment": {
            "model": model,
            "platform": "fixture-platform",
            "codex_command": ["codex"],
        },
        "bridge": {"worktree_cleaned": cleaned},
        "score": score,
        "failure_details": [],
    }


def pairs(count: int, **kwargs) -> tuple[dict[str, object], ...]:
    rows = []
    for repetition in range(1, count + 1):
        rows.extend(
            (
                artifact("raw", repetition, **kwargs),
                artifact("sigmap", repetition, **kwargs),
            )
        )
    return tuple(rows)


class PairedAnalysisTests(unittest.TestCase):
    def test_reports_deltas_directions_effects_and_tiny_sample_status(self) -> None:
        analysis = analyze_pairs(pairs(2))
        runtime = analysis["metrics"]["runtime_seconds"]

        self.assertEqual(analysis["complete_pair_count"], 2)
        self.assertEqual(runtime["direction_counts"]["improved"], 2)
        self.assertEqual(runtime["effect"]["median_delta"], -1.0)
        self.assertEqual(runtime["effect"]["median_relative_delta"], -0.5)
        self.assertEqual(
            runtime["confidence_interval"]["status"], "insufficient_evidence"
        )

    def test_confidence_interval_is_available_and_deterministic_at_ten_pairs(self) -> None:
        first = analyze_pairs(pairs(10))
        second = analyze_pairs(reversed(pairs(10)))
        first_interval = first["metrics"]["runtime_seconds"]["confidence_interval"]

        self.assertEqual(first, second)
        self.assertEqual(first_interval["status"], "available")
        self.assertEqual(first_interval["lower"], -1.0)
        self.assertEqual(first_interval["upper"], -1.0)

    def test_missing_zero_incomplete_and_duplicate_pairs_are_explicit(self) -> None:
        raw = artifact("raw", 1, runtime=0)
        sigmap = artifact("sigmap", 1, runtime=1)
        missing = artifact("raw", 2)
        del missing["score"]["runtime_seconds"]
        missing_peer = artifact("sigmap", 2)
        incomplete = artifact("raw", 3)
        analysis = analyze_pairs((raw, sigmap, missing, missing_peer, incomplete))
        runtime_pairs = analysis["metrics"]["runtime_seconds"]["pairs"]

        self.assertIsNone(runtime_pairs[0]["relative_delta"])
        self.assertEqual(runtime_pairs[1]["direction"], "unavailable")
        self.assertEqual(len(analysis["incomplete_pairs"]), 1)
        with self.assertRaisesRegex(PairingError, "duplicate raw"):
            analyze_pairs((raw, raw, sigmap))


class ComparisonTests(unittest.TestCase):
    def test_compares_compatible_strata_across_revisions_deterministically(self) -> None:
        baseline = pairs(2, revision="a" * 40)
        candidate = pairs(2, experiment="candidate", revision="b" * 40)
        comparison = compare_artifacts(baseline, candidate)

        self.assertTrue(comparison["compatible"])
        self.assertFalse(comparison["compatibility_override"])
        self.assertEqual(comparison["baseline"]["resolved_revisions"], ["a" * 40])
        self.assertEqual(comparison["candidate"]["resolved_revisions"], ["b" * 40])
        self.assertEqual(len(comparison["strata"]), 1)
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            write_comparison(first, comparison)
            write_comparison(second, comparison)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_rejects_incompatible_strata_unless_override_is_recorded(self) -> None:
        baseline = pairs(1)
        candidates = {
            "task": pairs(1, task="different-task"),
            "model": pairs(1, model="different-model"),
            "codex_command": pairs(1),
            "platform": pairs(1),
            "pack": pairs(1),
        }
        for row in candidates["codex_command"]:
            row["environment"]["codex_command"] = ["different-codex"]
        for row in candidates["platform"]:
            row["environment"]["platform"] = "different-platform"
        for row in candidates["pack"]:
            row["benchmark_pack"] = {
                "pack_id": "different-pack-v1",
                "pack_schema_version": 1,
                "manifest_sha256": "0" * 64,
            }
        for field, candidate_rows in candidates.items():
            with self.subTest(field=field):
                with self.assertRaisesRegex(ComparisonError, "strata differ"):
                    compare_artifacts(baseline, candidate_rows)

        candidate = candidates["model"]
        comparison = compare_artifacts(
            baseline,
            candidate,
            allow_incompatible=True,
        )
        self.assertFalse(comparison["compatible"])
        self.assertTrue(comparison["compatibility_override"])
        self.assertEqual(len(comparison["mismatches"]), 2)
        self.assertEqual(comparison["strata"], [])

    def test_cli_requires_and_records_incompatible_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline_dir = root / "baseline"
            candidate_dir = root / "candidate"
            baseline_dir.mkdir()
            candidate_dir.mkdir()
            for destination, rows in (
                (baseline_dir, pairs(1)),
                (candidate_dir, pairs(1, model="different-model")),
            ):
                for index, row in enumerate(rows):
                    (destination / f"{index}.json").write_text(
                        json.dumps(row), encoding="utf-8"
                    )
            rejected_output = io.StringIO()
            with contextlib.redirect_stdout(rejected_output):
                rejected = main(
                    (
                        "benchmark",
                        "compare",
                        str(baseline_dir),
                        str(candidate_dir),
                        "--json",
                    )
                )
            allowed_output = io.StringIO()
            with contextlib.redirect_stdout(allowed_output):
                allowed = main(
                    (
                        "benchmark",
                        "compare",
                        str(baseline_dir),
                        str(candidate_dir),
                        "--allow-incompatible",
                        "--json",
                    )
                )

        self.assertEqual(rejected, 2)
        self.assertEqual(allowed, 0)
        self.assertFalse(json.loads(rejected_output.getvalue())["compatible"])
        self.assertTrue(
            json.loads(allowed_output.getvalue())["compatibility_override"]
        )


class RegressionGateTests(unittest.TestCase):
    def policy(self, root: Path, thresholds: dict[str, object]) -> Path:
        path = root / "policy.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "schema_version": 1,
                    "policy_id": "fixture-policy",
                    "thresholds": thresholds,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return path

    def test_policy_is_strict_nonempty_and_has_valid_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = load_gate_policy(self.policy(root, {"max_runtime_ratio": 1.2}))
            self.assertEqual(valid.thresholds["max_runtime_ratio"], 1.2)
            cases = (
                ({}, "non-empty"),
                ({"unknown": 1}, "unknown fields"),
                ({"max_runtime_ratio": 0}, "finite number"),
                ({"require_worktree_cleanup": False}, "must be true"),
            )
            for thresholds, message in cases:
                with self.subTest(message=message):
                    with self.assertRaisesRegex(GateError, message):
                        load_gate_policy(self.policy(root, thresholds))

    def test_gate_checks_only_declared_thresholds_and_identifies_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = load_gate_policy(
                self.policy(
                    Path(directory),
                    {
                        "require_sigmap_correct_if_raw_correct": True,
                        "max_runtime_ratio": 0.4,
                        "max_input_tokens_ratio": 1.0,
                        "max_output_tokens_ratio": 1.0,
                        "max_unexpected_files": 0,
                        "require_worktree_cleanup": True,
                    },
                )
            )
        raw = artifact("raw", 1, runtime=2, passed=True)
        sigmap = artifact(
            "sigmap",
            1,
            runtime=1,
            passed=False,
            unexpected_files=["surprise.txt"],
            cleaned=False,
        )
        result = evaluate_gate(policy, (raw, sigmap))
        failures = [check for check in result["checks"] if not check["passed"]]

        self.assertFalse(result["passed"])
        self.assertEqual(result["check_count"], 6)
        self.assertEqual(
            {check["metric"] for check in failures},
            {"passed", "runtime_seconds", "unexpected_files", "worktree_cleaned"},
        )
        for failure in failures:
            self.assertEqual(failure["task_id"], "task")
            self.assertEqual(failure["pair_id"], "task-r001")
            self.assertIn("baseline", failure)
            self.assertIn("observed", failure)
            self.assertIn("threshold", failure)

    def test_zero_baseline_and_incomplete_pair_cannot_silently_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = load_gate_policy(
                self.policy(Path(directory), {"max_runtime_ratio": 1.0})
            )
        raw = artifact("raw", 1, runtime=0)
        sigmap = artifact("sigmap", 1, runtime=1)
        result = evaluate_gate(policy, (raw, sigmap))

        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"][0]["evaluable"])
        with self.assertRaisesRegex(GateError, "incomplete"):
            evaluate_gate(policy, (raw,))

    def test_cli_uses_success_regression_and_invalid_input_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            for index, row in enumerate(pairs(1)):
                (artifacts / f"{index}.json").write_text(
                    json.dumps(row), encoding="utf-8"
                )
            passing = self.policy(root, {"max_runtime_ratio": 1.0})
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                pass_exit = main(
                    ("benchmark", "gate", str(artifacts), str(passing), "--json")
                )
            failing = self.policy(root, {"max_runtime_ratio": 0.1})
            with contextlib.redirect_stdout(output):
                fail_exit = main(
                    ("benchmark", "gate", str(artifacts), str(failing), "--json")
                )
            invalid = self.policy(root, {})
            with contextlib.redirect_stdout(output):
                invalid_exit = main(
                    ("benchmark", "gate", str(artifacts), str(invalid), "--json")
                )

        self.assertEqual(pass_exit, 0)
        self.assertEqual(fail_exit, 50)
        self.assertEqual(invalid_exit, 2)


if __name__ == "__main__":
    unittest.main()
