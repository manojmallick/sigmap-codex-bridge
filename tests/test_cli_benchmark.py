import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from sigmap_codex_bridge.cli import main


class BenchmarkCliTests(unittest.TestCase):
    def test_validate_emits_normalized_json_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "task.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "repository": ".",
                        "revision": "HEAD",
                        "prompt": "Fix behavior",
                        "expected_behavior": "Task tests pass",
                        "test_command": ["python", "-m", "unittest"],
                    }
                ),
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(("benchmark", "validate", str(path), "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["task"]["schema_version"], 1)
        self.assertEqual(payload["task"]["test_command"][0], "python")

    def test_validate_returns_invalid_input_for_unsafe_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "task.yaml"
            path.write_text(
                """schema_version: 1
repository: .
revision: HEAD
prompt: Fix behavior
expected_behavior: Task tests pass
test_command: python -m unittest
""",
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(("benchmark", "validate", str(path), "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertFalse(payload["valid"])
        self.assertIn("argument array", payload["error"])

    def test_report_command_writes_both_deterministic_formats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = {
                "artifact_schema_version": 1,
                "experiment_id": "cli-fixture",
                "task_id": "one",
                "repetition": 1,
                "order_position": 1,
                "condition": "raw",
                "environment": {},
                "exact_command": [],
                "score": {
                    "passed": True,
                    "runtime_seconds": 1,
                    "input_tokens": 2,
                    "cached_input_tokens": 0,
                    "output_tokens": 3,
                    "patch_lines": 4,
                    "tool_events": 0,
                    "command_events": 1,
                },
                "failure_details": [],
            }
            (root / "run.json").write_text(json.dumps(artifact), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(("benchmark", "report", str(root), "--json"))

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(payload["valid"])
            self.assertEqual(payload["artifact_count"], 1)
            self.assertTrue((root / "report.json").is_file())
            self.assertTrue((root / "report.md").is_file())


if __name__ == "__main__":
    unittest.main()
