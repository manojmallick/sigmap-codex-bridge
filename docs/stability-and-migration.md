# Stable contracts and migration policy

SigMap Codex Bridge 1.0.0 freezes the public behavior below. Stability means
documented compatibility and failure behavior; it does not turn historical
benchmark evidence into a general performance claim.

## Stable public surfaces

| Surface | v1 commitment |
|---|---|
| Python | CPython 3.10–3.14 on macOS and Linux |
| Library | `Bridge`, `BridgeResult`, `ExitCode`, `ContextProvider`, `ContextResult`, `ContextStatus`, `RawContextProvider`, and `SigMapContextProvider` |
| One-off CLI | `demo`, `doctor`, `submission`, `provenance`, `run`, `verify`, and `cleanup` |
| Benchmark CLI | `validate`, `preflight`, `run`, `report`, `dashboard`, `compare`, `gate`, `pack`, and `execution` |
| Exit codes | `0`, `2`, `20`–`23`, `30`–`33`, `40`–`44`, and `50` retain their documented meanings throughout 1.x |
| Schemas | Benchmark task, artifact, report, pack, execution state, comparison, gate, provenance attestation, and dashboard v1 |
| Replay | `sigmap-bridge demo` remains zero-credit and checksum-linked to the frozen historical report |

Existing benchmark task v1, artifact v1, report v1, pack v1, and execution-state
v1 files remain accepted. Existing `Bridge.run(..., use_sigmap=False)` and
non-resumable `benchmark run` commands require no migration.

## Compatible changes

Patch releases may fix bugs without changing successful output semantics. Minor
releases may add optional fields, commands, enum values, provider implementations,
or schema versions. Readers must ignore documented additive fields they do not use.
Writers continue emitting the declared schema version.

The following require a new major version: removing or renaming a command or public
symbol, changing an existing exit-code meaning, making an optional argument required,
or changing the interpretation of an existing schema field.

## Deprecation policy

Deprecated 1.x behavior is documented and warned about for at least one minor
release. Removal occurs only in a new major version. Security fixes may disable an
unsafe path sooner, but the release notes must identify the exception and migration.

## Migrating from 0.9.x

No command or artifact migration is required:

1. Install 1.0.0 and rerun the existing test and replay commands.
2. Custom integrations may adopt the `ContextProvider` protocol; injected
   `SigMapContextProvider` instances continue to work unchanged.
3. Provenance signing is opt-in. Existing unsigned artifacts remain readable, but a
   verifier configured with `require_signed=True` rejects them.
4. Generate an aggregate view with `benchmark dashboard`; it does not rewrite the
   source artifacts or merge incompatible strata.

## Independent-replication boundary

The public replication pack remains valid, but 1.0.0 does not claim an external
independent result. Such evidence must be retained separately and pass pack
verification before that claim can be added later.
