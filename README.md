# SigMap Codex Bridge

SigMap Codex Bridge is a planned, reproducible A/B evaluation and evidence
layer for measuring how ranked repository context affects Codex task outcomes.

## Current status

This repository is implementing **v0.2.0**: isolated, traceable bridge runs. It
passes SigMap-ranked context to Codex through stdin in a detached Git worktree,
parses the Codex JSONL event stream, captures the resulting Git changes, and
appends a tamper-detecting audit record. It does not yet contain measured
benchmark results.

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

## Install

The package has no Python runtime dependencies. Python 3.10 or newer, Git,
Codex, Node.js, and SigMap are required for a live run.

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
