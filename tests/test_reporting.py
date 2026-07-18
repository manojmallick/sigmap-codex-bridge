import json
import tempfile
import unittest
from pathlib import Path

from sigmap_codex_bridge.reporting import load_artifacts, write_report


def artifact(task: str, condition: str, repetition: int, passed: bool) -> dict:
    return {
        "artifact_schema_version": 1,
        "experiment_id": "fixture",
        "task_id": task,
        "task_file": f"{task}.yaml",
        "resolved_revision": "abc123",
        "repetition": repetition,
        "pair_id": f"{task}-r{repetition:03d}",
        "condition": condition,
        "condition_order": ["raw", "sigmap"],
        "order_position": 1 if condition == "raw" else 2,
        "started_at": "2026-07-18T00:00:00Z",
        "finished_at": "2026-07-18T00:00:01Z",
        "exact_command": ["sigmap-bridge", "benchmark", "run"],
        "environment": {
            "bridge_version": "0.4.0",
            "python_version": "3.12.0",
            "platform": "fixture",
            "model": "fixture-model",
            "sandbox": "workspace-write",
            "codex_command": ["codex"],
            "sigmap_command": ["npx", "sigmap"],
        },
        "bridge": {},
        "score": {
            "passed": passed,
            "runtime_seconds": 2.0 if condition == "raw" else 1.0,
            "input_tokens": 20 if condition == "raw" else 10,
            "cached_input_tokens": 0,
            "output_tokens": 5,
            "patch_lines": 3,
            "tool_events": 1,
            "command_events": 2,
        },
        "failure_details": [] if passed else ["candidate tests failed"],
    }


class ReportingTests(unittest.TestCase):
    def test_report_is_byte_stable_and_preserves_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            rows = (
                artifact("one", "raw", 1, True),
                artifact("one", "sigmap", 1, False),
                artifact("one", "raw", 2, True),
                artifact("one", "sigmap", 2, True),
            )
            for index, row in enumerate(rows):
                (artifacts / f"{index}.json").write_text(
                    json.dumps(row), encoding="utf-8"
                )
            (artifacts / "unrelated.json").write_text("{}", encoding="utf-8")

            first_json = root / "first.json"
            first_md = root / "first.md"
            second_json = root / "second.json"
            second_md = root / "second.md"
            report = write_report(
                artifacts, json_path=first_json, markdown_path=first_md
            )
            write_report(artifacts, json_path=second_json, markdown_path=second_md)

            self.assertEqual(first_json.read_bytes(), second_json.read_bytes())
            self.assertEqual(first_md.read_bytes(), second_md.read_bytes())
            self.assertEqual(report["overall"]["raw"]["success_rate"], 1.0)
            self.assertEqual(report["overall"]["sigmap"]["success_rate"], 0.5)
            self.assertEqual(report["overall"]["sigmap"]["medians"]["input_tokens"], 10.0)
            self.assertEqual(
                report["comparisons"]["sigmap_to_raw_success_rate_ratio"], 0.5
            )
            self.assertEqual(report["paired_analysis"]["complete_pair_count"], 2)
            self.assertEqual(
                report["paired_analysis"]["correctness_transitions"],
                {
                    "both_passed": 1,
                    "raw_only_passed": 1,
                    "sigmap_only_passed": 0,
                    "both_failed": 0,
                },
            )
            self.assertEqual(
                report["paired_analysis"]["metrics"]["runtime_seconds"]["effect"][
                    "median_delta"
                ],
                -1.0,
            )
            self.assertIn("insufficient evidence", first_md.read_text(encoding="utf-8"))
            self.assertEqual(len(report["failures"]), 1)
            self.assertIn("candidate tests failed", first_md.read_text(encoding="utf-8"))
            self.assertEqual(len(load_artifacts(artifacts)), 4)

    def test_zero_denominators_produce_null_ratios(self) -> None:
        rows = (
            artifact("one", "raw", 1, False),
            artifact("one", "sigmap", 1, True),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, row in enumerate(rows):
                (root / f"{index}.json").write_text(
                    json.dumps(row), encoding="utf-8"
                )
            report = write_report(
                root,
                json_path=root / "report.json",
                markdown_path=root / "report.md",
            )

        self.assertIsNone(
            report["comparisons"]["sigmap_to_raw_success_rate_ratio"]
        )

    def test_incomplete_pair_is_retained_but_excluded_from_aggregates(self) -> None:
        rows = (
            artifact("one", "raw", 1, True),
            artifact("one", "sigmap", 1, True),
            artifact("one", "raw", 2, False),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, row in enumerate(rows):
                (root / f"{index}.json").write_text(
                    json.dumps(row), encoding="utf-8"
                )
            report = write_report(
                root,
                json_path=root / "report.json",
                markdown_path=root / "report.md",
            )
            markdown = (root / "report.md").read_text(encoding="utf-8")

        self.assertEqual(report["artifact_count"], 3)
        self.assertEqual(report["overall"]["raw"]["attempts"], 1)
        self.assertEqual(report["overall"]["sigmap"]["attempts"], 1)
        self.assertEqual(
            report["paired_analysis"]["excluded_incomplete_attempt_count"], 1
        )
        self.assertEqual(len(report["failures"]), 1)
        self.assertIn("Excluded incomplete attempts from aggregate summaries: 1", markdown)


if __name__ == "__main__":
    unittest.main()
