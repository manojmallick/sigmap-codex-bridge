# SigMap Codex Bridge

SigMap Codex Bridge is a planned, reproducible A/B evaluation and evidence
layer for measuring how ranked repository context affects Codex task outcomes.

## Current status

This repository is implementing **v0.4.0**: a reproducible paired benchmark on
top of isolated, traceable bridge runs. It alternates raw and SigMap condition
order, pins each pair to one resolved commit and configuration, retains every
attempt as a raw JSON artifact, and regenerates machine-readable and Markdown
reports without using retrieved context as correctness ground truth.

The hypothesis is:

> Relevant repository context should improve task success or reduce the work
> Codex needs to reach a correct result.

No performance improvement is claimed until a reproducible benchmark with
independent correctness checks has been implemented and run.

## Project documents

- [`SIGMAP_CODEX_BRIDGE_PLAN.md`](SIGMAP_CODEX_BRIDGE_PLAN.md) — original
  pre-implementation planning artifact
- [`VERSIONED_COMMIT_PLAN.md`](VERSIONED_COMMIT_PLAN.md) — staged delivery and
  acceptance plan
- [`docs/adr/0001-codex-context-injection.md`](docs/adr/0001-codex-context-injection.md)
  — initial Codex integration decision
- [`docs/benchmark-specification.md`](docs/benchmark-specification.md) — task
  contract, metric definitions, and threats to validity

## Install

Python 3.10 or newer and Git are required. PyYAML is installed with the package;
Codex, Node.js, and SigMap are additionally required for a live bridge run.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .
```

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
