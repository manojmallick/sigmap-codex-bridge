"""Versioned benchmark task loading and validation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


SCHEMA_VERSION = 1


class BenchmarkValidationError(ValueError):
    """Raised when a benchmark task does not satisfy the public contract."""


@dataclass(frozen=True)
class BenchmarkTask:
    schema_version: int
    repository: str
    revision: str
    prompt: str
    expected_behavior: str
    test_command: tuple[str, ...]
    setup_command: tuple[str, ...] | None = None
    static_check_commands: tuple[tuple[str, ...], ...] = ()
    allowed_files: tuple[str, ...] = ()
    expected_files: tuple[str, ...] = ()
    expected_symbols: tuple[str, ...] = ()
    timeout_seconds: float = 900.0
    repetitions: int = 1

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["test_command"] = list(self.test_command)
        value["setup_command"] = (
            list(self.setup_command) if self.setup_command is not None else None
        )
        value["static_check_commands"] = [
            list(command) for command in self.static_check_commands
        ]
        value["allowed_files"] = list(self.allowed_files)
        value["expected_files"] = list(self.expected_files)
        value["expected_symbols"] = list(self.expected_symbols)
        return value


_REQUIRED_FIELDS = {
    "schema_version",
    "repository",
    "revision",
    "prompt",
    "expected_behavior",
    "test_command",
}
_OPTIONAL_FIELDS = {
    "setup_command",
    "static_check_commands",
    "allowed_files",
    "expected_files",
    "expected_symbols",
    "timeout_seconds",
    "repetitions",
}


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkValidationError(f"{field} must be a non-empty string")
    return value


def _command(value: object, field: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raise BenchmarkValidationError(
            f"{field} must be an argument array, not a shell command string"
        )
    if not isinstance(value, Sequence) or not value:
        raise BenchmarkValidationError(f"{field} must be a non-empty argument array")
    command = tuple(_require_text(part, f"{field} item") for part in value)
    return command


def _string_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise BenchmarkValidationError(f"{field} must be an array of strings")
    items = tuple(_require_text(item, f"{field} item") for item in value)
    if len(items) != len(set(items)):
        raise BenchmarkValidationError(f"{field} must not contain duplicates")
    return items


def _load_document(path: Path) -> Mapping[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise BenchmarkValidationError(f"Cannot read task file: {error}") from error

    try:
        if path.suffix.lower() == ".json":
            value = json.loads(text)
        elif path.suffix.lower() in {".yaml", ".yml"}:
            value = yaml.safe_load(text)
        else:
            raise BenchmarkValidationError("Task file must use .json, .yaml, or .yml")
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        raise BenchmarkValidationError(f"Cannot parse task file: {error}") from error
    if not isinstance(value, Mapping):
        raise BenchmarkValidationError("Task document must be an object")
    return value


def load_benchmark_task(path: str | Path) -> BenchmarkTask:
    """Load a strict YAML or JSON benchmark task into the versioned model."""

    task_path = Path(path).resolve()
    value = _load_document(task_path)
    fields = set(value)
    missing = sorted(_REQUIRED_FIELDS - fields)
    unknown = sorted(fields - _REQUIRED_FIELDS - _OPTIONAL_FIELDS)
    if missing:
        raise BenchmarkValidationError(f"Missing required fields: {', '.join(missing)}")
    if unknown:
        raise BenchmarkValidationError(f"Unknown fields: {', '.join(unknown)}")

    version = value["schema_version"]
    if not isinstance(version, int) or isinstance(version, bool):
        raise BenchmarkValidationError("schema_version must be an integer")
    if version != SCHEMA_VERSION:
        raise BenchmarkValidationError(
            f"Unsupported schema_version {version}; expected {SCHEMA_VERSION}"
        )

    raw_repository = _require_text(value["repository"], "repository")
    repository_path = Path(raw_repository).expanduser()
    if not repository_path.is_absolute():
        repository_path = task_path.parent / repository_path

    timeout = value.get("timeout_seconds", 900.0)
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or timeout <= 0
    ):
        raise BenchmarkValidationError("timeout_seconds must be greater than zero")

    repetitions = value.get("repetitions", 1)
    if (
        not isinstance(repetitions, int)
        or isinstance(repetitions, bool)
        or repetitions < 1
    ):
        raise BenchmarkValidationError("repetitions must be a positive integer")

    setup = (
        _command(value["setup_command"], "setup_command")
        if "setup_command" in value
        else None
    )
    static_value = value.get("static_check_commands", [])
    if not isinstance(static_value, Sequence) or isinstance(static_value, (str, bytes)):
        raise BenchmarkValidationError("static_check_commands must be an array")

    return BenchmarkTask(
        schema_version=version,
        repository=str(repository_path.resolve()),
        revision=_require_text(value["revision"], "revision"),
        prompt=_require_text(value["prompt"], "prompt"),
        expected_behavior=_require_text(
            value["expected_behavior"], "expected_behavior"
        ),
        setup_command=setup,
        test_command=_command(value["test_command"], "test_command"),
        static_check_commands=tuple(
            _command(command, "static_check_commands item")
            for command in static_value
        ),
        allowed_files=_string_list(value.get("allowed_files", []), "allowed_files"),
        expected_files=_string_list(
            value.get("expected_files", []), "expected_files"
        ),
        expected_symbols=_string_list(
            value.get("expected_symbols", []), "expected_symbols"
        ),
        timeout_seconds=float(timeout),
        repetitions=repetitions,
    )
