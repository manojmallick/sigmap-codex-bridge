import json
import tempfile
import unittest
from pathlib import Path

import yaml

from sigmap_codex_bridge.benchmark import (
    BenchmarkValidationError,
    load_benchmark_task,
)


class BenchmarkSchemaTests(unittest.TestCase):
    def test_published_json_schemas_parse(self) -> None:
        schema_root = Path(__file__).resolve().parents[1] / "schemas"
        names = (
            "benchmark-task-v1.schema.json",
            "benchmark-pack-v1.schema.json",
            "benchmark-comparison-v1.schema.json",
            "benchmark-execution-state-v1.schema.json",
            "benchmark-gate-policy-v1.schema.json",
            "benchmark-gate-result-v1.schema.json",
            "benchmark-run-artifact-v1.schema.json",
            "benchmark-report-v1.schema.json",
        )
        for name in names:
            with self.subTest(name=name):
                value = json.loads((schema_root / name).read_text(encoding="utf-8"))
                self.assertEqual(value["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def task_value(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "repository": "./repo",
            "revision": "main",
            "prompt": "Fix the parser",
            "expected_behavior": "Malformed input is rejected",
            "setup_command": ["python", "-m", "pip", "install", "."],
            "test_command": ["python", "-m", "unittest", "tests.test_parser"],
            "static_check_commands": [["ruff", "check", "src"]],
            "allowed_files": ["src/parser.py", "tests/test_parser.py"],
            "expected_files": ["src/parser.py"],
            "expected_symbols": ["parse_input"],
            "timeout_seconds": 120,
            "repetitions": 3,
        }

    def test_yaml_and_json_load_into_the_same_versioned_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = self.task_value()
            json_path = root / "task.json"
            yaml_path = root / "task.yaml"
            json_path.write_text(json.dumps(value), encoding="utf-8")
            yaml_path.write_text(yaml.safe_dump(value), encoding="utf-8")

            json_task = load_benchmark_task(json_path)
            yaml_task = load_benchmark_task(yaml_path)

        self.assertEqual(json_task, yaml_task)
        self.assertEqual(json_task.schema_version, 1)
        self.assertEqual(json_task.test_command[0], "python")
        self.assertEqual(json_task.repetitions, 3)

    def test_rejects_unknown_fields_and_shell_command_strings(self) -> None:
        cases = []
        unknown = self.task_value()
        unknown["ground_truth_context"] = "retrieved text"
        cases.append((unknown, "Unknown fields"))
        shell_string = self.task_value()
        shell_string["test_command"] = "python -m unittest"
        cases.append((shell_string, "argument array"))

        with tempfile.TemporaryDirectory() as directory:
            for index, (value, message) in enumerate(cases):
                with self.subTest(message=message):
                    path = Path(directory) / f"task-{index}.json"
                    path.write_text(json.dumps(value), encoding="utf-8")
                    with self.assertRaisesRegex(BenchmarkValidationError, message):
                        load_benchmark_task(path)

    def test_rejects_invalid_version_timeout_and_repetitions(self) -> None:
        cases = (
            ("schema_version", 2, "Unsupported schema_version"),
            ("timeout_seconds", 0, "greater than zero"),
            ("repetitions", 0, "positive integer"),
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, (field, value, message) in enumerate(cases):
                with self.subTest(field=field):
                    task = self.task_value()
                    task[field] = value
                    path = Path(directory) / f"invalid-{index}.json"
                    path.write_text(json.dumps(task), encoding="utf-8")
                    with self.assertRaisesRegex(BenchmarkValidationError, message):
                        load_benchmark_task(path)


if __name__ == "__main__":
    unittest.main()
