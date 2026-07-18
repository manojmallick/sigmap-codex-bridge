# Five-minute judge quickstart

The fastest path is a **zero-credit replay** of the measured v0.4 benchmark
report packaged in the wheel. It does not run Codex or SigMap, touch Git, make
network requests, or claim to produce fresh benchmark evidence.

## 1. Install from a clean checkout

Supported: macOS and Linux with CPython 3.10 through 3.14.

```bash
git clone https://github.com/manojmallick/sigmap-codex-bridge.git
cd sigmap-codex-bridge
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
```

## 2. Replay the packaged evidence

Run from outside the checkout to prove that package resources, rather than
working-tree files, supply the demo:

```bash
cd /tmp
sigmap-bridge demo
sigmap-bridge demo --json > sigmap-bridge-replay.json
```

The first line is deliberately explicit:

```text
ZERO-CREDIT REPLAY — no live Codex, SigMap, Git, or network calls
```

The JSON result includes `mode: "replay"`, `live_calls: 0`, the complete
measured aggregate, and replay events for each task. The packaged report is an
exact byte copy of
`benchmarks/results/build-week-2026-07-18/report.json`. Its SHA-256 digest is:

```text
689698a2525cb77142a3aae33295ef6d7de18a6d0bb848c85546f70c61acf490
```

The demo verifies that digest before displaying any result. The manifest also
links the replay to experiment `build-week-2026-07-18`, source revision
`504e823853459fef0c66e0b02915b4fc59ec3151`, and report commit
`d7c9877906af083ae0724e50175f859386a52e7b`.

## 3. Check live-run readiness

This diagnostic is local and does not run a benchmark:

```bash
cd /path/to/a/clean/git/repository
sigmap-bridge doctor
sigmap-bridge doctor --json
```

It distinguishes unsupported Python/platform versions, missing or broken
executables, invalid or dirty repositories, a missing or stale SigMap index,
and absent Codex authentication. Use `--require-live` when automation should
exit nonzero unless every live prerequisite is ready.

## Optional live path

A live bridge or benchmark run is separate from the replay. It requires Git,
a current SigMap index, a working authenticated Codex CLI, network access, and
may consume API or subscription credits. First satisfy `sigmap-bridge doctor`,
then follow the commands in the repository README and benchmark methodology.

The opt-in executable smoke test is also kept out of default tests:

```bash
SIGMAP_BRIDGE_LIVE_SMOKE=1 python -m unittest tests.test_live_smoke -v
```

Windows, alternative Python implementations, and containers without the
required external CLIs are not currently supported for live runs. The
zero-credit replay remains usable wherever the Python package can be installed,
but CI guarantees it only on the supported macOS/Linux CPython matrix.
