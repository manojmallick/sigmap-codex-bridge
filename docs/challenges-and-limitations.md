# Challenges, mitigations, and limitations

This diary records concrete failures encountered while producing the checked-in
benchmark and the judge-ready CLI. It is evidence about the current prototype,
not a claim that every environment will fail in the same way.

## Challenges encountered

### Git worktree sandbox permission

The first real preflight smoke run could not write Git's `.git/worktrees`
metadata because the execution sandbox denied it. The same command was rerun
with the necessary permission, passed, and its recoverable bridge-owned lease
was explicitly cleaned. The source repository was clean afterward.

### Broken Codex launcher

The Homebrew Codex launcher at `/opt/homebrew/bin/codex` existed but failed
because its platform binary was missing. Using the working Codex binary shipped
with the ChatGPT application unblocked the benchmark. This is why `doctor`
checks execution with `--version`, rather than treating a path on `PATH` as
sufficient.

### Unsupported Apple Python selected by `/usr/bin/env`

One launcher selected Apple Python 3.9, which cannot evaluate the project's
modern union type annotations. The benchmark pinned a supported interpreter.
The package now declares and tests CPython 3.10 through 3.14 explicitly.

### SigMap launcher behavior under a child process

`npx sigmap` timed out when invoked from one Python subprocess even though the
direct `/opt/homebrew/bin/sigmap` executable worked. The benchmark used the
direct executable. `doctor --sigmap-command` allows the same explicit override.

### Context delivery location

An early SigMap query printed a banner to stdout while the usable context was
written to `.context/query-context.md`. The provider was corrected and tested
so the bridge consumes the actual context payload rather than incidental CLI
text.

### A negative efficiency result was retained

For the “artifact run status” task, median input was 534,456 tokens raw and
606,285 with SigMap. That result was not removed or averaged away. It appears
in every checked-in aggregate and in the zero-credit replay.

## Current limitations

- The measured sample is three repository-maintenance tasks with three paired
  repetitions each. It is not evidence of general model-quality improvement.
- All 18 candidate runs passed, so the data demonstrates an efficiency
  difference in this sample but cannot establish a correctness advantage.
- v0.7.0 provides a hash-locked pack for an unrelated public repository, but it
  intentionally contains no paid live result. Independent execution and review
  of fresh evidence are still needed before claiming external replication.
- Runtime and token use can vary with service load, model changes, cache state,
  and Codex CLI behavior even when task order alternates.
- Parallel pair execution preserves condition isolation and deterministic
  report ordering, but concurrent external-service load can still change
  runtime, token use, and stochastic model output.
- Paired median/MAD summaries reduce sensitivity to outliers but do not remove
  task-selection or external-service bias. The 10-pair bootstrap boundary is an
  operational disclosure rule, not a claim of statistical power.
- Compatibility overrides make cross-environment differences visible; they do
  not turn mismatched model, CLI, platform, task, or pack strata into
  like-for-like evidence.
- The replay is historical and deliberately receives zero benchmark credit. It
  verifies package integrity and makes existing evidence easy to inspect; only
  a new live run can produce fresh evidence.
- Live operation is supported and CI-tested on macOS and Linux with CPython
  3.10–3.14. Windows and alternative Python implementations are unverified.
- Codex authentication and credit use are controlled by the external CLI and
  account. The bridge cannot guarantee availability, cost, or model stability.
- Audit hashes and local checkpoints detect ordinary artifact mutation but are
  not signed or externally anchored attestations against an actor who can
  rewrite every local record.
- Resumable state uses atomic local-file replacement and exact worktree leases;
  it is not a distributed lock, durable database, signed record, or protection
  against a second process deliberately mutating the same execution directory.
