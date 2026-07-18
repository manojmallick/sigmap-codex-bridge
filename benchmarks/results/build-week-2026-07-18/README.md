# Build Week paired benchmark — 2026-07-18

This directory contains a fresh run of three pinned maintenance tasks, two
conditions, and three repetitions: 18 retained artifacts in total. Condition
order alternated per repetition. Every attempt used source revision
`504e823853459fef0c66e0b02915b4fc59ec3151`.

## Exact command

```bash
PYTHONPATH=src /opt/homebrew/bin/python3 -m sigmap_codex_bridge benchmark run \
  benchmarks/tasks/artifact-run-status.yaml \
  benchmarks/tasks/markdown-comparisons.yaml \
  benchmarks/tasks/report-failure-exit.yaml \
  --experiment-id build-week-2026-07-18 \
  --output-dir benchmark_runs/build-week-2026-07-18 \
  --model gpt-5.6-sol \
  --codex-command /Applications/ChatGPT.app/Contents/Resources/codex \
  --context-timeout 120 \
  --sandbox workspace-write \
  --json
```

Environment recorded in every artifact:

- SigMap Codex Bridge `0.4.0`
- Codex CLI `0.145.0-alpha.18`, model `gpt-5.6-sol`
- SigMap `8.18.0`
- Python `3.14.6`
- Darwin `25.5.0` on arm64
- Codex sandbox `workspace-write`

## Results

Both conditions passed all nine candidate regression suites and Ruff checks.
The overall SigMap-to-raw median runtime ratio was `0.749090287129336`; the
median total-input ratio was `0.733633557631846`. Total input includes cached
input, which is recorded separately in `report.json` and each raw artifact.

| Task | Raw success | SigMap success | Median runtime raw / SigMap (s) | Median input raw / SigMap |
|---|---:|---:|---:|---:|
| Artifact run status | 3/3 | 3/3 | 228.288 / 216.274 | 534,456 / 606,285 |
| Markdown comparisons | 3/3 | 3/3 | 249.089 / 141.404 | 766,538 / 402,740 |
| Report failure exit | 3/3 | 3/3 | 266.106 / 183.294 | 937,367 / 509,165 |
| **Overall per-run median** | **9/9** | **9/9** | **249.089 / 186.590** | **766,538 / 562,358** |

Task 1 is a negative efficiency result for input: its SigMap median was 71,829
tokens higher than raw despite a modest runtime reduction. The raw task-1 runs
and several task-2 runs also changed files outside their allow-lists; those
precision penalties remain in the artifacts.

## Reproduce the report

From a clean checkout with the package available:

```bash
sigmap-bridge benchmark report \
  benchmarks/results/build-week-2026-07-18/artifacts \
  --json-output benchmarks/results/build-week-2026-07-18/report.json \
  --markdown-output benchmarks/results/build-week-2026-07-18/report.md \
  --json
```

The report generator sorts inputs deterministically. Re-running this command
without changing the raw artifacts produces byte-identical outputs.

## Limitations

- These are three maintenance tasks in one small Python repository at one
  revision, not a representative software-engineering population.
- The primary correctness gate is Codex completion plus the repository's
  already-passing regression suite. It can detect regressions but is not a
  hidden feature-acceptance suite. Expected-file targeting metrics expose
  no-op or off-target behavior as secondary evidence.
- Three repetitions per condition are enough to retain variability but not to
  establish statistical significance.
- Cached input dominated several runs. Total and cached input are both retained;
  comparisons here use the report's total-input definition.
- Results reflect one machine, date, Codex CLI/model, and service environment.
  Reproduction may differ as those external conditions change.
