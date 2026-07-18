# SigMap Codex Bridge

SigMap Codex Bridge is a planned, reproducible A/B evaluation and evidence
layer for measuring how ranked repository context affects Codex task outcomes.

## Current status

This repository is implementing **v0.1.0**: a contract-tested bridge core. It
passes SigMap-ranked context to Codex through stdin and parses the resulting
Codex JSONL event stream. It does not yet contain measured benchmark results.

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

## Install the baseline

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

## License

MIT
