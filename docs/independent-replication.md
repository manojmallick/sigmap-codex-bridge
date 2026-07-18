# Independent replication guide

Benchmark packs let an independent evaluator reproduce a paired raw/SigMap
experiment without editing SigMap Codex Bridge. A pack fixes the target
repository, immutable revision, declared license, task bytes, environment,
setup command, repetition count, runner settings, and schema versions.

The included reference pack targets PyPA's public `sampleproject` repository at
commit `621e4974ca25ce531773def586ba3ed8e736b3fc`. The repository declares the MIT
license. It is third-party code: PyPA does not maintain, endorse, or validate
SigMap Codex Bridge.

## Validate and inspect without model credits

From a clean checkout with the package installed:

```bash
sigmap-bridge benchmark pack validate \
  benchmark_packs/pypa-sampleproject-v1/pack.yaml --json
sigmap-bridge benchmark pack export \
  benchmark_packs/pypa-sampleproject-v1/pack.yaml \
  /tmp/pypa-sampleproject-v1.tar.gz --json
sigmap-bridge benchmark pack preflight \
  benchmark_packs/pypa-sampleproject-v1/pack.yaml \
  --workspace /tmp/sigmap-replication --json
```

Validation checks the strict manifest and every task digest. Export writes a
byte-stable archive with normalized tar metadata and a checksum inventory.
Preflight clones the public target, checks out the full pinned revision, and
runs the unchanged baseline tests in a disposable detached worktree. None of
these commands launches Codex or spends model credits.

## Run a fresh complete pair

The live command below is opt-in. It requires working authenticated Codex and
SigMap CLIs, network access, and may consume model credits:

```bash
sigmap-bridge benchmark pack run \
  benchmark_packs/pypa-sampleproject-v1/pack.yaml \
  --workspace /tmp/sigmap-replication \
  --output-dir /tmp/pypa-sampleproject-evidence \
  --experiment-id independent-YYYY-MM-DD \
  --model MODEL_ID \
  --codex-command /path/to/codex \
  --json
```

The output directory must be empty. Each artifact is stamped with the pack ID,
evidence kind, pack schema, and exact manifest digest. The runner retains both
conditions and seals all output files in `evidence-index.json`; a failed or
interrupted run remains visible and is not silently promoted to complete
evidence.

Verify transferred or retained evidence with:

```bash
sigmap-bridge benchmark pack verify-evidence \
  benchmark_packs/pypa-sampleproject-v1/pack.yaml \
  /tmp/pypa-sampleproject-evidence --json
```

Verification rejects missing or changed files, hash drift, duplicate attempts,
incomplete raw/SigMap pairs, undeclared tasks, wrong revisions or schemas, and
pack provenance mismatches. Evidence declared as `replication` therefore
cannot be silently presented as the project's original Build Week evidence.

## Create a pack for another repository

Create versioned task YAML files first, then initialize a pack with a public
HTTPS repository, a full commit ID, and its SPDX license identifier:

```bash
sigmap-bridge benchmark pack init ./my-pack/pack.yaml \
  --pack-id my-project-v1 \
  --evidence-kind replication \
  --repository-url https://github.com/OWNER/REPOSITORY.git \
  --revision FULL_COMMIT_ID \
  --license MIT \
  --task ./tasks/task-one.yaml \
  --platform linux \
  --repetitions 3 \
  --json
```

Commands in tasks and setup are argument arrays, not shell strings. Pack paths
must remain inside the pack directory. Mutable branch or tag names, missing or
ambiguous licenses, unsupported schema versions, and changed task bytes fail
validation.

## Interpretation and non-claims

The bundled pack is a reproducible experiment definition, not a favorable
result. No live sampleproject result is checked in for v0.7.0. Any replication
report must identify its model, Codex/SigMap versions, platform, and environment
and must retain negative results. A single small repository and task cannot
establish a general correctness or productivity advantage; runtime and token
use can change with service load, caches, model revisions, and CLI behavior.
