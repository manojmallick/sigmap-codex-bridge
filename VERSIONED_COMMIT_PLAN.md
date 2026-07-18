# SigMap Codex Bridge — Versioned Commit Plan

## Product decision

Build the project as a reproducible **Codex context A/B evaluation and evidence
layer**, not only as a subprocess wrapper.

The primary user-facing command should eventually look like:

```bash
sigmap-bridge compare benchmarks/tasks/jwt-null.yaml --repo ./spring-security-samples
```

It should run the same task in isolated Git worktrees, once without SigMap and
once with SigMap, then report correctness, tests, files changed, token usage,
runtime, and the exact context hash used by the SigMap condition.

## Constraints discovered during plan review

- Codex accepts piped data as additional context when a prompt argument is also
  supplied. Use stdin; do not depend on the proposed `--context-file` flag.
- Use `codex exec --json` and parse its JSONL events for the thread ID, tool
  activity, completion state, and token usage.
- Current SigMap exposes `ask`, `--query ... --json`, `verify`, `verify-plan`,
  `review-pr`, a Codex adapter, and Codex MCP installation. The reviewed CLI
  help does not expose the proposed `sigmap judge` command, so the benchmark
  must not depend on it.
- Do not score a raw run against empty SigMap context. That makes the comparison
  circular. Correctness must come from independent task oracles such as tests,
  expected symbols/files, and patch constraints.
- Do not reset benchmark repositories with `git checkout .`. Use disposable
  worktrees or copies so the two conditions cannot contaminate each other.
- The audit log must verify a real hash chain. Checking only that a stored hash
  is 16 characters long does not prove integrity.

## Commit rules

- Keep every commit runnable or documentation-only.
- Never mix product code, benchmark results, and submission copy in one commit.
- Commit generated benchmark results only after the exact command used to
  produce them is committed and reproducible.
- Tag only after the acceptance gate for that version passes.
- Preserve the primary Codex build task/session so the `/feedback` session ID
  and commit history tell the same chronological story.

## v0.0.0 — Decision record and repository baseline

Goal: establish an honest starting point before implementation.

1. `docs: record bridge hypothesis and delivery constraints`
   - Add the original plan and this versioned plan.
   - State the one claim: relevant context should improve task success or reduce
     the work needed to reach success.
2. `chore: initialize project metadata and ignore runtime artifacts`
   - Add `LICENSE`, `.gitignore`, and a minimal `pyproject.toml`.
   - Ignore `.context/`, audit JSONL files, temporary worktrees, generated
     primers, Python caches, and benchmark run artifacts.
3. `docs: add architecture decision for stdin context injection`
   - Add an ADR documenting why stdin + `codex exec --json` replaces the draft
     `--context-file` design.

Acceptance gate:

- Repository installs in an empty virtual environment.
- No benchmark result or performance claim is committed yet.

Tag: `v0.0.0`

## v0.1.0 — Contract-tested bridge core

Goal: prove the real Codex and SigMap process contracts before adding features.

1. `test: add fake Codex and SigMap process fixtures`
   - Provide deterministic executable fixtures for success, timeout, malformed
     output, missing binary, and non-zero exit cases.
2. `feat: add typed subprocess runner and result models`
   - Separate process execution from business logic.
   - Capture stdout, stderr, exit code, duration, command metadata, and timeout.
3. `feat: add SigMap context provider`
   - Check index readiness and return explicit `ready`, `unavailable`, or
     `failed` states.
   - Prefer deterministic/machine-readable retrieval where possible.
4. `feat: run Codex with prompt plus stdin context`
   - Invoke `codex exec --json` with explicit sandbox policy.
   - Parse JSONL for thread ID, completion/failure, file changes, and usage.
5. `feat: expose run and --no-sigmap CLI modes`
   - Provide stable exit codes and JSON output.
   - Never silently label a fallback run as SigMap-grounded.
6. `test: cover bridge success and failure contracts`
   - Unit-test parsing and fallbacks without consuming Codex credits.
   - Add one opt-in local smoke test for the real CLIs.

Acceptance gate:

- `sigmap-bridge run` works with and without context.
- Missing SigMap, missing index, timeout, malformed JSONL, and Codex failure are
  distinguishable in output and exit status.
- The full unit suite passes without network or live model access.

Tag: `v0.1.0`

## v0.2.0 — Git-aware execution and real audit integrity

Goal: make each run traceable and safe to compare.

1. `feat: capture repository state with Git porcelain`
   - Record base commit, dirty-state precondition, and final name-status diff.
   - Correctly detect created, modified, renamed, and deleted files.
2. `feat: add isolated worktree lifecycle`
   - Create a unique worktree per run from the same base commit.
   - Clean up only worktrees created by the current run.
3. `feat: add hash-chained bridge audit records`
   - Store full SHA-256 context digest, previous-entry digest, entry digest,
     run ID, base commit, condition, Codex thread ID, exit state, and usage.
   - Avoid storing raw context or secrets by default.
4. `feat: verify audit chain from the CLI`
   - Add `sigmap-bridge verify` that recomputes every entry and reports the
     first broken link.
5. `test: detect audit tampering and worktree leakage`

Acceptance gate:

- Changing, deleting, or reordering an audit entry fails verification.
- Two runs from the same base commit cannot see each other's patches.
- Worktree cleanup is scoped and recoverable after interruption.

Tag: `v0.2.0`

## v0.3.0 — Independent benchmark specification

Goal: define success before running the expensive experiment.

1. `feat: define versioned benchmark task schema`
   - Each YAML/JSON task specifies repository revision, prompt, setup command,
     test command, expected behavior, allowed/expected files or symbols, timeout,
     and repetitions.
2. `feat: add task validation and preflight command`
   - Reject missing revisions, dirty sources, unavailable commands, and tasks
     whose baseline tests already fail.
3. `feat: add independent correctness scorers`
   - Primary: task-specific tests pass.
   - Secondary: target-file precision/recall, patch size, static checks, runtime,
     input/cached/output tokens, and number of tool/command events.
4. `test: validate scorers against known good and bad patches`
5. `docs: document benchmark threats to validity`
   - Include stochasticity, prompt leakage, task selection bias, cache effects,
     order effects, and the distinction between retrieval relevance and patch
     correctness.

Acceptance gate:

- A hand-authored correct patch passes and a plausible wrong patch fails.
- Scoring never uses SigMap context as the raw condition's ground truth.
- Every metric has a documented definition and source field.

Tag: `v0.3.0`

## v0.4.0 — Reproducible A/B benchmark

Goal: produce defensible evidence rather than a one-off demo number.

1. `feat: run paired raw and SigMap benchmark conditions`
   - Randomize or alternate condition order.
   - Use the same base revision, task prompt, sandbox, timeout, and model.
2. `feat: add repetitions and raw run artifacts`
   - Target three tasks × two conditions × three repetitions if budget allows.
   - Keep every run record; do not retain only the best result.
3. `feat: generate machine-readable and Markdown reports`
   - Report success rate and median per-run metrics.
   - Keep failures visible and avoid ratio claims when the denominator is zero.
4. `test: reproduce report from checked-in fixture runs`
5. `bench: add fresh Build Week benchmark results`
   - This is the first commit allowed to contain real measured numbers.
   - Include environment metadata and the exact command used.

Acceptance gate:

- A clean checkout can regenerate the report from raw artifacts.
- At least one correctness metric and one efficiency metric are reported.
- README claims exactly match the generated report, including negative results.

Tag: `v0.4.0`

## v0.5.0 — Judge-ready developer experience

Goal: let a judge install and verify the core experience quickly.

1. `feat: package sigmap-bridge console commands`
   - Support the documented Python versions and macOS/Linux initially.
   - Provide clear diagnostics for Codex auth, SigMap index, and Git state.
2. `feat: add zero-credit demo mode`
   - Replay checked-in fixture events and reports without calling a live model.
   - Clearly label replay output so it cannot be mistaken for a live run.
3. `ci: test supported platforms and package installation`
4. `docs: write install quickstart and five-minute judge path`
5. `docs: add exact challenges and limitations diary`
   - Use errors actually observed during implementation.

Acceptance gate:

- Fresh install, fixture demo, and tests work from a clean checkout.
- A live smoke-test path is documented separately from the no-credit replay.
- Supported and unsupported platforms are explicit.

Tag: `v0.5.0`

## v0.6.0 — Build Week submission candidate

Goal: freeze the evidence and tell one coherent story.

1. `docs: publish measured results and Codex collaboration narrative`
   - Add fresh generated numbers, primary Codex session ID placeholder, dated
     commit evidence, key decisions, and where Codex accelerated the work.
2. `docs: add architecture and benchmark diagrams`
3. `docs: finalize sub-three-minute demo script`
   - Open on the paired result, then show isolation, correctness, usage, and
     audit verification.
4. `chore: add release checklist and submission metadata`
5. `release: prepare Build Week submission candidate`
   - Update version and changelog only after all prior gates pass.

Acceptance gate:

- Video, README, code, and benchmark report show the same commands and numbers.
- Repository license, test path, supported platforms, and no-rebuild judge path
  are present.
- The primary `/feedback` session ID is captured.
- Submission is complete before the official deadline buffer.

Tag: `v0.6.0-build-week`

## v1.0.0 — Post-submission stable release

Do not spend Build Week time on this unless every v0.6.0 gate is already green.

Candidate commits:

1. `feat: add resumable benchmark runs and bounded concurrency`
2. `feat: add provider interface for alternative context strategies`
3. `feat: export signed provenance attestations`
4. `feat: publish aggregate comparison dashboard`
5. `docs: define stable CLI and artifact schemas`

Tag only after backward-compatibility, migration, and cross-platform tests pass.

## Recommended critical path for July 18–20

If time is constrained, execute only this sequence:

1. v0.0.0 baseline.
2. v0.1.0 bridge contract and one live smoke test.
3. v0.2.0 isolated worktrees plus honest audit verification.
4. v0.3.0 one fully validated benchmark task.
5. v0.4.0 three tasks, reducing repetitions only if credit/time requires it.
6. v0.5.0 clean-install path and fixture replay.
7. v0.6.0 README, video, `/feedback`, and submission.

Cut v1.0 features first. Never cut independent correctness tests, worktree
isolation, raw artifacts, or fresh benchmark results; those are the credibility
of the project.
