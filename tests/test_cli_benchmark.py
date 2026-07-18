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


if __name__ == "__main__":
    unittest.main()
