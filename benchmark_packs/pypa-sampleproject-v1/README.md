# PyPA sampleproject replication pack

This pack defines one independent paired experiment against the public
[`pypa/sampleproject`](https://github.com/pypa/sampleproject) repository, pinned
to commit `621e4974ca25ce531773def586ba3ed8e736b3fc`. The target repository declares
the MIT license. PyPA is a third party and does not endorse this project.

The task asks both conditions to add the same small function and regression
test. Its unchanged baseline passes before either candidate runs. The pack uses
`python3`, permits macOS and Linux, requires one complete raw/SigMap pair, and
contains no live or replayed result.

From the SigMap Codex Bridge repository:

```bash
sigmap-bridge benchmark pack validate \
  benchmark_packs/pypa-sampleproject-v1/pack.yaml --json
sigmap-bridge benchmark pack preflight \
  benchmark_packs/pypa-sampleproject-v1/pack.yaml --json
```

See [`docs/independent-replication.md`](../../docs/independent-replication.md)
for export, live-run, evidence verification, caveats, and pack-authoring steps.
