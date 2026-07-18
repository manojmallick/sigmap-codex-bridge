"""Independent correctness and efficiency scoring for benchmark observations."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .benchmark import BenchmarkTask


@dataclass(frozen=True)
class BenchmarkObservation:
    """Observable run outputs; deliberately contains no retrieved context."""

    test_passed: bool
    static_check_results: tuple[bool, ...] = ()
    changed_files: tuple[str, ...] = ()
    touched_symbols: tuple[str, ...] = ()
    lines_added: int = 0
    lines_deleted: int = 0
    runtime_seconds: float = 0.0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    tool_events: int = 0
    command_events: int = 0


@dataclass(frozen=True)
class BenchmarkScore:
    passed: bool
    tests_passed: bool
    static_checks_passed: bool
    target_file_precision: float
    target_file_recall: float
    target_symbol_precision: float
    target_symbol_recall: float
    unexpected_files: tuple[str, ...]
    changed_file_count: int
    lines_added: int
    lines_deleted: int
    patch_lines: int
    runtime_seconds: float
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    tool_events: int
    command_events: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _precision_recall(
    actual: set[str], expected: set[str]
) -> tuple[float, float]:
    overlap = actual & expected
    precision = len(overlap) / len(actual) if actual else (1.0 if not expected else 0.0)
    recall = len(overlap) / len(expected) if expected else 1.0
    return precision, recall


def score_observation(
    task: BenchmarkTask, observation: BenchmarkObservation
) -> BenchmarkScore:
    """Score only declared targets and observable process/repository outputs."""

    changed = set(observation.changed_files)
    expected_files = set(task.expected_files)
    expected_symbols = set(task.expected_symbols)
    file_precision, file_recall = _precision_recall(changed, expected_files)
    symbol_precision, symbol_recall = _precision_recall(
        set(observation.touched_symbols), expected_symbols
    )
    unexpected = changed - set(task.allowed_files) if task.allowed_files else set()
    static_passed = all(observation.static_check_results)

    return BenchmarkScore(
        passed=observation.test_passed,
        tests_passed=observation.test_passed,
        static_checks_passed=static_passed,
        target_file_precision=file_precision,
        target_file_recall=file_recall,
        target_symbol_precision=symbol_precision,
        target_symbol_recall=symbol_recall,
        unexpected_files=tuple(sorted(unexpected)),
        changed_file_count=len(changed),
        lines_added=observation.lines_added,
        lines_deleted=observation.lines_deleted,
        patch_lines=observation.lines_added + observation.lines_deleted,
        runtime_seconds=observation.runtime_seconds,
        input_tokens=observation.input_tokens,
        cached_input_tokens=observation.cached_input_tokens,
        output_tokens=observation.output_tokens,
        tool_events=observation.tool_events,
        command_events=observation.command_events,
    )
