# Changelog

All notable changes to SigMap Codex Bridge are documented here. Versions before
v0.6.0 correspond to the staged pull requests linked in the repository.

## [1.0.0] — 2026-07-21

### Added

- Public `ContextProvider` protocol with backward-compatible built-in raw and
  SigMap providers and fail-closed alternative-provider behavior.
- Versioned HMAC-SHA256 provenance envelopes, deterministic canonical payloads,
  key identities, verification constraints, strict schema, CLI commands, and a
  documented threat model.
- Reproducible JSON and Markdown evidence dashboards generated from retained
  artifact directories without merging incompatible strata or hiding negative,
  failed, or incomplete results.
- Stable compatibility, deprecation, and migration policy for CLI commands,
  exit codes, benchmark schemas, replay behavior, and extension contracts.

### Changed

- Package version and maturity classifier advanced to the stable 1.0.0 line.
- Build Week metadata now records the real public video URL and passes the
  fail-closed external-readiness gate.

### Evidence boundary

- Historical Build Week evidence remains frozen and is not presented as a new
  v1.0.0 benchmark run.
- The replication pack remains available, but no independent external result is
  claimed by this release.

## [0.9.0] — 2026-07-18

### Added

- Strict versioned execution-state snapshots with atomic checkpoints,
  artifact reconciliation, configuration-drift detection, and safe resume.
- Pair-aware bounded concurrency with sequential raw/SigMap conditions and
  isolated, uniquely leased worktrees.
- Pair, cumulative runtime, and cumulative token budgets with explicit
  in-flight overshoot records and no monetary-cost estimate.
- Exact-lease execution diagnosis/recovery commands and crash-transition,
  concurrency, budget, corruption, CLI, and report regression coverage.

### Changed

- Package version advanced to 0.9.0 while benchmark task, run-artifact,
  report, pack, and frozen submission contracts remain compatible.
- Reports retain incomplete attempts and failures but exclude them from
  aggregate condition metrics until their pair is complete.

## [0.8.0] — 2026-07-18

### Added

- Deterministic within-pair correctness transitions, runtime/input/output
  deltas, direction counts, median/MAD effects, and honest uncertainty status.
- Compatibility-stratified experiment comparison with explicit, recorded
  overrides for task, model, Codex command, platform, or pack mismatches.
- Strict regression-policy and result contracts covering correctness,
  efficiency, unexpected files, and cleanup with dedicated exit code `50`.
- Interpretation guidance and an executable conservative policy example.

### Changed

- Package version advanced to 0.8.0 while historical v1 artifacts and the
  frozen v0.6.0 submission evidence remain valid.
- Report schema v1 accepts the additive `paired_analysis` field; samples below
  10 comparable pairs state `insufficient_evidence` instead of emitting an
  interval.

## [0.7.0] — 2026-07-18

### Added

- Strict portable benchmark-pack manifests with immutable repository, license,
  task hash, environment, runner, and schema contracts.
- Pack initialization, validation, deterministic export, clean-clone preflight,
  paired execution, evidence sealing, and evidence verification commands.
- Pack provenance in new artifacts without breaking standalone v1 artifacts.
- A no-result replication pack for the public MIT-licensed PyPA sampleproject
  repository and an independent replicator guide.

### Changed

- Package version advanced to 0.7.0.
- Submission validation accepts the intact historical v0.6.0 candidate from a
  newer package while still rejecting malformed or future metadata versions.
- Limitations now distinguish the available independent pack from fresh
  third-party result evidence, which has not yet been produced.

## [0.6.0] — 2026-07-18

### Added

- Frozen Build Week measured-results and Codex collaboration narrative.
- Architecture, paired benchmark, and evidence-boundary diagrams.
- Rehearsable 2:40 demo script and aligned Devpost submission copy.
- Machine-readable submission metadata and integrity/readiness validator.
- Explicit release checklist that blocks on real `/feedback`, video, and
  Devpost values.

### Changed

- Package version advanced to 0.6.0 for the submission candidate.
- README now leads with the measured claim and links every judge artifact.

## [0.5.0] — 2026-07-18

- Added the installable zero-credit replay, live-readiness doctor, package-data
  verification, five-minute judge quickstart, limitations diary, and supported
  macOS/Linux Python CI matrix.

## [0.4.0] — 2026-07-18

- Added reproducible paired runs, fresh 18-attempt evidence, deterministic
  reports, exact environments/commands, and retained negative results.

## [0.3.0] — 2026-07-18

- Added strict benchmark tasks, preflight, independent correctness scoring,
  published schemas, and metric/threat documentation.

## [0.2.0] — 2026-07-18

- Added detached worktree isolation, scoped recovery, atomic audit checkpoints,
  tamper detection, and stable failure codes.

## [0.1.0] — 2026-07-18

- Added contract-tested Git, SigMap, Codex, process, and CLI boundaries.

## [0.0.0] — 2026-07-18

- Established the honest package baseline, schemas, architecture decision, and
  staged delivery plan.
