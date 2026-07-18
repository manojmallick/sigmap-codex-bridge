# SigMap Codex Bridge

SigMap Codex Bridge is a reproducible A/B evaluation and evidence layer for
measuring how ranked repository context affects Codex task outcomes. Built for
OpenAI Build Week 2026.

## Current status

This repository is preparing **v0.6.0**, the Build Week submission candidate.
The code, measured report, README, demo script, and submission copy use one
frozen result and one claim. Repository-owned gates are complete only when CI
passes; the final submission remains explicitly blocked until real `/feedback`,
video, and Devpost values replace the null fields in submission metadata.

The hypothesis is:

> Relevant repository context should improve task success or reduce the work
> Codex needs to reach a correct result.

A fresh paired run on 2026-07-18 retained all 18 attempts: both conditions
passed 9/9 candidate regression/static checks. Across all runs, median runtime
was 249.089 seconds raw versus 186.590 seconds with SigMap; median total input
was 766,538 versus 562,358 tokens. These are small-sample maintenance-task
results, not a general model-quality claim, and one task used more input with
SigMap.

| Task | Raw success | SigMap success | Median runtime raw / SigMap (s) | Median input raw / SigMap |
|---|---:|---:|---:|---:|
| Artifact run status | 3/3 | 3/3 | 228.288 / 216.274 | 534,456 / 606,285 |
| Markdown comparisons | 3/3 | 3/3 | 249.089 / 141.404 | 766,538 / 402,740 |
| Report failure exit | 3/3 | 3/3 | 266.106 / 183.294 | 937,367 / 509,165 |
| **Overall per-run median** | **9/9** | **9/9** | **249.089 / 186.590** | **766,538 / 562,358** |

The checked-in [report](benchmarks/results/build-week-2026-07-18/report.md),
[machine-readable aggregate](benchmarks/results/build-week-2026-07-18/report.json),
and [methodology](benchmarks/results/build-week-2026-07-18/README.md) contain
the complete environment, command, limitations, and all raw artifacts.

The retained artifacts also contain 18 unique Codex thread IDs, nine raw runs
with context disabled, nine SigMap runs with context ready, and 18 worktrees
reported cleaned. The [measured-results and Codex narrative](docs/submission/measured-results-and-codex.md)
ties those counts to dated commits and preserves the exact integration failures
that changed the implementation.

## Project documents

- [`SIGMAP_CODEX_BRIDGE_PLAN.md`](SIGMAP_CODEX_BRIDGE_PLAN.md) — original
  pre-implementation planning artifact
- [`VERSIONED_COMMIT_PLAN.md`](VERSIONED_COMMIT_PLAN.md) — staged delivery and
  acceptance plan
- [`docs/adr/0001-codex-context-injection.md`](docs/adr/0001-codex-context-injection.md)
  — initial Codex integration decision
- [`docs/benchmark-specification.md`](docs/benchmark-specification.md) — task
  contract, metric definitions, and threats to validity
- [`docs/judge-quickstart.md`](docs/judge-quickstart.md) — five-minute install,
  zero-credit replay, and separate opt-in live path
- [`docs/challenges-and-limitations.md`](docs/challenges-and-limitations.md) —
  concrete failure diary and current scope limits
- [`docs/submission/architecture.md`](docs/submission/architecture.md) — bridge,
  paired benchmark, and evidence-boundary diagrams
- [`docs/submission/demo-script.md`](docs/submission/demo-script.md) — timed
  2:40 recording script that opens on the measured result
- [`docs/submission/devpost-submission.md`](docs/submission/devpost-submission.md)
  — aligned Build Week submission copy
- [`docs/submission/release-checklist.md`](docs/submission/release-checklist.md) —
  repository and external release gates
- [`submission/build-week-2026.json`](submission/build-week-2026.json) —
  machine-readable evidence, judge commands, deadline, and readiness status

## Install

Supported live environments are macOS and Linux with CPython 3.10 through
3.14. PyYAML is installed with the package; Git, Codex, and SigMap are
additionally required only for a live bridge run.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .
```

## Zero-credit judge demo

The fastest judge path is offline and consumes no model credits. It replays the
measured report packaged in the installed wheel and labels itself as historical
evidence, never as a fresh run:

```bash
cd /tmp
sigmap-bridge demo
sigmap-bridge demo --json
```

The packaged report is checksum-linked to the checked-in v0.4 result. The
[five-minute judge quickstart](docs/judge-quickstart.md) gives the exact digest,
provenance, expected output, and install-from-clean-checkout steps.

Check whether a machine is ready for a genuinely live run without launching
one:

```bash
sigmap-bridge doctor --repo ./your-repo
sigmap-bridge doctor --repo ./your-repo --require-live --json
```

`doctor` distinguishes missing, broken, unauthenticated, dirty, stale, and
unsupported states with an actionable fix. Live runs require external CLIs,
network access, and may consume Codex/API credits; they are never part of the
zero-credit replay.

Validate that every published number still matches the frozen report and see
which external Build Week fields remain:

```bash
sigmap-bridge submission validate submission/build-week-2026.json
sigmap-bridge submission validate submission/build-week-2026.json --require-ready
```

The first command succeeds when repository evidence is internally consistent.
The second deliberately exits nonzero until the real `/feedback` session ID,
video URL, and Devpost URL are present and the metadata status is `ready`.

## Run

Run with SigMap context (the default):

```bash
sigmap-bridge run "Fix the JWT validation bug" --repo ./your-repo --json
```

Run the explicit raw condition:

```bash
sigmap-bridge run "Fix the JWT validation bug" --repo ./your-repo --no-sigmap --json
```

The bridge fails closed when SigMap was requested but its index is unavailable;
it never silently runs the raw condition as a grounded success.

Every normal run is pinned to the source repository's `HEAD` in a dedicated
worktree. Uncommitted source changes are recorded as a dirty precondition but
are not copied into the run. Successful cleanup removes only the bridge-owned,
Git-recognized worktree lease.

Verify the audit chain and its atomic head checkpoint:

```bash
sigmap-bridge verify --repo ./your-repo --json
```

Recover one worktree left by an interrupted process:

```bash
sigmap-bridge cleanup <run-id> --repo ./your-repo --json
```

Validate a versioned benchmark task, then check its clean baseline in an
isolated worktree:

```bash
sigmap-bridge benchmark validate benchmarks/task.yaml --json
sigmap-bridge benchmark preflight benchmarks/task.yaml --json
```

Task commands are argument arrays, never shell strings. Preflight rejects dirty
source repositories, missing revisions or executables, setup failures, and task
tests that already fail at the declared revision.

Run every declared repetition as a complete raw/SigMap pair. The first
condition alternates per repetition to reduce order effects:

```bash
sigmap-bridge benchmark run benchmarks/tasks/*.yaml \
  --experiment-id build-week-2026-07-18 \
  --model MODEL_ID \
  --codex-command /path/to/codex \
  --context-timeout 120 \
  --output-dir benchmark_runs \
  --json
```

Regenerate byte-stable JSON and Markdown summaries from the retained artifacts:

```bash
sigmap-bridge benchmark report benchmark_runs --json
```

Each raw artifact records the resolved revision, pair and order identifiers,
environment and exact command, context/Codex process outcomes, candidate tests,
static checks, repository changes, independent score, cleanup result, and all
failure details. Reports include condition success rates, median efficiency
metrics, and every failed run. Ratios are `null` when the raw denominator is
zero.

Audit records contain the full SHA-256 digest of context, not raw context or
task text. The local chain and checkpoint detect ordinary modification,
deletion, insertion, and reordering. They are not a signed or externally
anchored attestation against an actor able to rewrite both audit files.

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Codex completed successfully |
| `2` | Invalid task or repository |
| `20` | SigMap executable unavailable |
| `21` | SigMap index missing or empty |
| `22` | SigMap timed out |
| `23` | SigMap retrieval failed |
| `30` | Codex executable unavailable |
| `31` | Codex timed out |
| `32` | Codex JSONL malformed or incomplete |
| `33` | Codex reported or returned a failure |
| `40` | Git inspection or change capture failed |
| `41` | Isolated worktree creation failed |
| `42` | Scoped worktree cleanup failed |
| `43` | Audit append failed |
| `44` | Audit verification failed |

## License

MIT
