# Resumable execution and cost controls

v0.9.0 adds an opt-in execution state to standalone `benchmark run`. Existing
non-resumable runs and benchmark-pack workflows remain unchanged. The state is
local control data, not benchmark evidence and not a signed trust record.

## Start and resume

Choose dedicated state, artifact, and worktree paths:

```bash
sigmap-bridge benchmark run benchmarks/tasks/*.yaml \
  --experiment-id maintenance-ab-01 \
  --output-dir ./benchmark-runs/maintenance-ab-01 \
  --worktree-root ./benchmark-worktrees/maintenance-ab-01 \
  --state-file ./benchmark-state/maintenance-ab-01.json \
  --max-workers 2 --max-pairs 6 \
  --max-runtime-seconds 3600 --max-total-tokens 500000 --json
```

The initial artifact directory must be absent or empty. To continue, repeat the
same task files and execution settings and add `--resume`:

```bash
sigmap-bridge benchmark run benchmarks/tasks/*.yaml \
  --experiment-id maintenance-ab-01 \
  --output-dir ./benchmark-runs/maintenance-ab-01 \
  --worktree-root ./benchmark-worktrees/maintenance-ab-01 \
  --state-file ./benchmark-state/maintenance-ab-01.json \
  --resume --max-workers 3 --max-pairs 12 --json
```

Worker count and budgets may change on resume. Task contents, revisions,
experiment identity, artifact/worktree paths, sandbox, model, Codex command,
context timeout, and starting condition may not. A changed task hash or setting
fails closed before a new attempt starts.

## Checkpoint and artifact rules

The execution-state-v1 JSON contract is strict: unknown fields, duplicate
identities, unsafe artifact paths, invalid transitions, and inconsistent
digests are rejected. Each state transition is written to a temporary file,
flushed, and atomically replaces the previous checkpoint.

Every pair has deterministic raw and SigMap attempt identities. Its conditions
run sequentially; separate pairs may run concurrently. Each attempt owns a
unique worktree lease and one deterministic artifact filename. Resume never
overwrites or reruns a completed artifact.

If a process exits after writing an artifact but before checkpointing it,
resume validates its experiment, task, revision, pair, condition, position,
pack provenance, and contents before marking that attempt complete. If an
artifact recorded as complete is missing or its SHA-256 digest changed, resume
fails closed. Retained partial-pair artifacts and failures remain visible, but
reports exclude incomplete pairs from aggregate condition metrics.

## Budget semantics

- `--max-pairs` reserves capacity before launching a pair, so it has no
  concurrency overshoot.
- `--max-runtime-seconds` uses cumulative measured Codex attempt runtime.
- `--max-total-tokens` uses cumulative input plus output tokens. Cached input is
  already part of input and is not added again.
- Limits are evaluated at complete-pair boundaries. Pairs already in flight
  finish, so runtime and token usage can exceed their thresholds.
- A partially completed pair is finished on resume before starting new pairs,
  even if its earlier attempt already crossed a limit.

A controlled stop exits successfully with `status: stopped`. `stop_reason`
records the limit, threshold, observed value, overshoot, and in-flight count.
`monetary_cost` is always `null`: provider pricing, caching discounts, and
billing context are deliberately outside this evidence contract.

## Diagnose and recover

Inspect only leases referenced by running attempts in one state file:

```bash
sigmap-bridge benchmark execution diagnose ./benchmark-state/maintenance-ab-01.json --json
```

The result distinguishes missing, active, stale, and invalid/tampered leases.
To remove only valid active or stale leases referenced by that state and reset
their attempts to pending:

```bash
sigmap-bridge benchmark execution recover ./benchmark-state/maintenance-ab-01.json --json
```

Recovery does not scan or delete unrelated worktrees. Invalid lease metadata
fails closed. A normal `--resume` performs the same exact-lease cleanup for an
interrupted running attempt before continuing.

## Limitations

Atomic replacement protects against ordinary process interruption on a local
filesystem; it is not a distributed lock or durable database transaction.
Concurrent external mutation of the state or artifact directory is unsupported.
Parallel pairs can experience different external-service load, and the model
remains stochastic, so concurrency equivalence means identical contracts and
deterministic report ordering—not byte-identical runtimes or outputs.
