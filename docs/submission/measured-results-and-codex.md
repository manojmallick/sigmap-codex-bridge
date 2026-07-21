# Measured results and Codex collaboration

## The one claim

> Codex works better when it does not have to guess which files matter.

The Build Week evidence supports a deliberately narrower statement: on three
maintenance tasks in this repository, both conditions passed every candidate
test and static check, while the SigMap condition used lower median runtime and
total input overall. This is an efficiency result from a small paired sample,
not a general correctness or model-quality claim.

## Frozen measured result

The 2026-07-18 experiment retained 18 artifacts: three tasks, two conditions,
and three repetitions. Each pair used source revision
`504e823853459fef0c66e0b02915b4fc59ec3151`; condition order alternated by
repetition.

| Overall median | Raw | SigMap | SigMap change |
|---|---:|---:|---:|
| Candidate passes | 9/9 | 9/9 | equal |
| Runtime | 249.089 s | 186.590 s | 25.1% lower |
| Total input | 766,538 tokens | 562,358 tokens | 26.6% lower |
| Command events | 20 | 15 | 25.0% lower |
| Output | 7,169 tokens | 4,587 tokens | 36.0% lower |

The negative result is preserved: “artifact run status” used 534,456 median
input tokens raw and 606,285 with SigMap, even though its SigMap runtime was
lower. The sample is too small for statistical significance and all 18 runs
passed, so it does not establish a correctness advantage.

Source of truth:

- Experiment: `build-week-2026-07-18`
- Frozen report commit: `d7c9877906af083ae0724e50175f859386a52e7b`
- Report SHA-256:
  `689698a2525cb77142a3aae33295ef6d7de18a6d0bb848c85546f70c61acf490`
- Machine-readable report:
  `benchmarks/results/build-week-2026-07-18/report.json`

The zero-credit `sigmap-bridge demo` command verifies this checksum and replays
the historical report. It makes no live Codex, SigMap, Git, or network calls
and receives no credit as a fresh benchmark.

## What Codex did

Codex was the implementation partner across the staged repository history:

1. `d2dbdc3` through `c5a68e5` established the package, schemas, architecture,
   and honest placeholder boundary.
2. `3a3b8f3` through `7da520f` added isolated Git worktrees and the hash-chained
   Bridge Audit Log with tamper tests.
3. `405e244` through `7a1c06c` defined strict task contracts, preflight, and
   correctness scoring that intentionally excludes SigMap context as ground
   truth.
4. `504e823`, `584855d`, and `d069c54` built and repaired the paired runner,
   including explicit run status and a supported-Python pin discovered during
   real execution.
5. `d7c9877` retained all 18 raw attempts and generated the report above.
6. `9abdf70` made the evidence installable as a zero-credit replay and added
   diagnostics after real launcher, authentication, and stale-index failures.

Countable benchmark collaboration evidence:

- 18 retained Codex attempts and 18 unique Codex thread IDs.
- 9 raw runs with context explicitly disabled.
- 9 SigMap runs with context status `ready`.
- 18 bridge-owned worktrees reported cleaned.
- 3 distinct task prompts, each executed in both conditions three times.

Codex also accelerated failure diagnosis. The exact friction—including the
Homebrew launcher `ENOENT`, Apple Python 3.9 selection, worktree permission
failure, and `npx sigmap` child-process timeout—is preserved in the
[challenges diary](../challenges-and-limitations.md).

## Primary feedback session

The primary `/feedback` session is
`019f75cb-5dfc-7f03-a9c1-94f86dd92c8c`. The real public video and Devpost URLs
are recorded in `submission/build-week-2026.json`. Run:

```bash
sigmap-bridge submission validate submission/build-week-2026.json --require-ready
```

to enforce the complete external-readiness gate.
