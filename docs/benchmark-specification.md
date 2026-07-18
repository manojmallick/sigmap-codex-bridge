# Benchmark specification and validity

Version 1 benchmark tasks are YAML or JSON documents governed by
[`schemas/benchmark-task-v1.schema.json`](../schemas/benchmark-task-v1.schema.json).
The loader rejects unknown fields and command strings. Commands are argument
arrays and are always executed without a shell.

```yaml
schema_version: 1
repository: ../target-repository
revision: 0123456789abcdef
prompt: Reject expired tokens during authentication.
expected_behavior: Expired tokens fail the task-specific authentication tests.
setup_command: [python, -m, pip, install, -e, .]
test_command: [python, -m, unittest, tests.test_auth]
static_check_commands:
  - [ruff, check, src, tests]
allowed_files: [src/auth.py, tests/test_auth.py]
expected_files: [src/auth.py, tests/test_auth.py]
expected_symbols: [validate_token]
timeout_seconds: 300
repetitions: 3
```

Paths in `repository` are resolved relative to the task file. `revision` must
resolve to a commit. Preflight requires the source repository to be clean,
creates a detached worktree at that commit, runs optional setup followed by the
task test, and then removes only that leased worktree. A task is rejected when
the revision or an executable is unavailable, setup fails, or the baseline task
test fails before any candidate patch is applied.

## Metric definitions

| Metric | Definition | Source field |
|---|---|---|
| `passed`, `tests_passed` | True only when the task-specific test command exits successfully after the candidate patch. This is the primary correctness result. | `BenchmarkObservation.test_passed` |
| `static_checks_passed` | True when every configured static-check process exits successfully; true when none are configured. | `static_check_results` |
| `target_file_precision` | Expected changed files divided by all changed files. Empty actual and expected sets score 1. | `changed_files`, task `expected_files` |
| `target_file_recall` | Expected changed files actually changed divided by all expected files. No declared expected files score 1. | `changed_files`, task `expected_files` |
| `target_symbol_precision/recall` | The same set calculations for symbols identified by the benchmark runner's diff analysis. | `touched_symbols`, task `expected_symbols` |
| `unexpected_files` | Changed files outside `allowed_files`; empty when no allow-list is declared. | `changed_files`, task `allowed_files` |
| `changed_file_count` | Number of distinct changed paths. | `changed_files` |
| `lines_added`, `lines_deleted`, `patch_lines` | Git numstat additions, deletions, and their sum. | `lines_added`, `lines_deleted` |
| `runtime_seconds` | Wall-clock duration of the candidate run. | `runtime_seconds` |
| Token metrics | Codex input, cached-input, and output token counts. | `input_tokens`, `cached_input_tokens`, `output_tokens` |
| Event metrics | Completed Codex JSONL items classified as tool calls or command executions. | `tool_events`, `command_events` |

The scorer accepts only the declared task contract and observable run outputs.
It has no field for raw or SigMap-ranked context. Retrieval relevance may help
explain a run, but it is never correctness ground truth.

## Paired execution and retained evidence

`sigmap-bridge benchmark run` preflights each task once, resolves its revision
to a commit, and creates a new detached worktree for every condition. Each
one-based repetition contains exactly one raw and one SigMap run. With the
default raw starting condition, the orders are `raw, sigmap` for odd
repetitions and `sigmap, raw` for even repetitions.

Both members of a pair use the same resolved revision, prompt, setup and test
commands, sandbox, timeout, and model setting. Candidate tests and static checks
run inside the candidate worktree before its recoverable lease is cleaned.
Context retrieval failure is retained as a failed SigMap attempt and never
silently falls back to raw.

Every attempted run is atomically written using the
[`benchmark-run-artifact-v1`](../schemas/benchmark-run-artifact-v1.schema.json)
contract. The artifact contains process stdout/stderr and provenance but the
independent `score` object contains no context field. Interrupted experiments
therefore retain all artifacts completed before the interruption rather than a
selected best run.

`sigmap-bridge benchmark report` reads only retained artifacts and writes a
[`benchmark-report-v1`](../schemas/benchmark-report-v1.schema.json) JSON report
plus a Markdown rendering. Inputs are sorted by experiment, task, repetition,
and within-pair position, so identical inputs produce byte-identical reports.
Success rates use all attempted runs. Efficiency metrics use medians, failures
remain enumerated, and comparisons are `null` when their raw denominator is
zero.

## Threats to validity

- **Stochasticity:** model output varies. Preserve all repetitions and report
  distributions or medians rather than selecting the best run.
- **Prompt leakage:** prompts, expected behavior, fixtures, or context can reveal
  the intended patch. Review tasks for answer-bearing text before execution.
- **Task-selection bias:** a small or hand-picked suite may favor one condition.
  Define selection rules before observing results and keep failures visible.
- **Cache effects:** dependency, model, and context caches can change runtime and
  token measurements. Record cached input separately and use equivalent setup.
- **Order effects:** warm caches and service conditions can favor the later run.
  Randomize or alternate paired condition order.
- **Retrieval versus patch correctness:** relevant retrieved files do not prove a
  correct patch, and an irrelevant-looking retrieval does not prove failure.
  Task-specific tests remain the primary outcome.
