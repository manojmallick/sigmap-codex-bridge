# SigMap Codex Bridge

SigMap Codex Bridge is a planned, reproducible A/B evaluation and evidence
layer for measuring how ranked repository context affects Codex task outcomes.

## Current status

This repository is at **v0.0.0**: an honest project baseline. It contains the
product hypothesis, delivery plan, packaging metadata, and initial architecture
decision. It does not yet contain the bridge implementation or measured
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

## Install the baseline

The baseline package has no runtime dependencies and intentionally exposes no
CLI yet. Python 3.10 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .
```

## License

MIT
