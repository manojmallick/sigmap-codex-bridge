# Paired analysis, compatible comparison, and regression gates

v0.8.0 analyzes raw and SigMap attempts as pairs. This preserves the experiment
design: a runtime or token change is calculated between conditions for the same
task, repetition, revision, and pair identity before any summary is produced.

## Paired report fields

`sigmap-bridge benchmark report` adds `paired_analysis` to report schema v1.
Older artifact-schema-v1 files still load; when a historical artifact has no
`pair_id`, the reporter derives the runner's stable `<task>-rNNN` identity.
Duplicate conditions are rejected. Incomplete pairs and missing metrics remain
visible and are excluded from numeric effects.

For runtime, input tokens, and output tokens, each complete pair records:

- the raw and SigMap values;
- `delta = SigMap - raw`;
- `relative_delta = delta / raw`, or `null` when raw is zero;
- a direction, where lower is better: `improved`, `unchanged`, `regressed`, or
  `unavailable`.

Each metric also reports direction counts, the median paired delta, the median
relative delta, and median absolute deviation. These are descriptive robust
summaries, not proof that one condition is generally better.

The 95% interval is a deterministic 10,000-resample paired bootstrap percentile
interval for the median delta. It is emitted only with at least 10 comparable
pairs. Below that boundary the machine-readable status is
`insufficient_evidence`; the tool does not emit an interval or a significance
claim. Ten is an operational minimum, not a guarantee that a sample is
representative or adequately powered.

## Compare experiments

Compare two retained artifact directories across revisions:

```bash
sigmap-bridge benchmark compare \
  ./baseline-artifacts ./candidate-artifacts \
  --output comparison.json --json
```

Like-for-like strata include task ID, model, Codex command, platform, benchmark
pack ID, pack schema version, and pack manifest digest. The resolved revision
is deliberately reported rather than used as a compatibility key, because a
revision change is the intended comparison axis.

Different strata fail with invalid-input exit code `2`. An evaluator may make
the mismatch visible instead of rejecting it:

```bash
sigmap-bridge benchmark compare \
  ./baseline-artifacts ./candidate-artifacts \
  --allow-incompatible --output comparison.json --json
```

The result then sets `compatible: false`, sets `compatibility_override: true`,
and lists every baseline-only and candidate-only stratum. An override permits
inspection; it does not make the experiments like-for-like.

## Apply explicit regression gates

No built-in threshold can fail a build. A gate evaluates only fields declared
in a strict policy:

```yaml
schema_version: 1
policy_id: project-ci-v1
thresholds:
  require_sigmap_correct_if_raw_correct: true
  max_runtime_ratio: 1.25
  max_input_tokens_ratio: 1.20
  max_output_tokens_ratio: 1.20
  max_unexpected_files: 0
  require_worktree_cleanup: true
```

Run it against a complete artifact directory:

```bash
sigmap-bridge benchmark gate \
  ./artifacts ./benchmark-policy.yaml \
  --output gate-result.json --json
```

Every check identifies the task, pair, metric, raw baseline, SigMap observation,
comparison value, and declared threshold. A missing metric or zero raw
denominator makes a declared ratio check unevaluable and failed rather than
silently skipped. Incomplete or duplicate pairs and invalid policies are input
errors.

Exit codes are stable:

| Code | Meaning |
|---:|---|
| `0` | Every declared check passed |
| `2` | Policy or artifact input is invalid |
| `50` | At least one declared regression threshold failed |

[`benchmarks/gates/conservative-example-v1.yaml`](../benchmarks/gates/conservative-example-v1.yaml)
is an executable format example against the frozen Build Week artifacts. Its
limits are illustrative, not recommended universal defaults.

## Interpretation limits

Pairing reduces some run-to-run noise but cannot control service load, caches,
model updates, CLI changes, or repository/task selection. A favorable median,
direction count, or interval does not establish causality or general model
quality. Cross-environment overrides must be disclosed, negative results must
remain in the artifacts, and project-specific thresholds should be chosen
before evaluating the candidate whenever practical.
