# Build Week submission copy

## Title

SigMap Codex Bridge

## Tagline

Codex works better when it does not have to guess which files matter.

## Track

Developer Tools

## Description

SigMap Codex Bridge is a reproducible A/B evaluation and evidence layer for
testing whether ranked repository context changes Codex outcomes. It pins raw
and SigMap conditions to the same Git revision and configuration, alternates
condition order, runs each attempt in an isolated detached worktree, scores
correctness independently from retrieved context, retains every raw artifact,
and regenerates deterministic reports.

In the 2026-07-18 Build Week experiment, both conditions passed 9/9 candidate
test and static-check suites. Overall median runtime was 249.089 seconds raw
and 186.590 seconds with SigMap; median total input was 766,538 and 562,358
tokens respectively. One task used more input with SigMap, and that negative
result remains prominent. This three-task sample supports a narrow efficiency
observation, not a general model-quality or correctness claim.

Judges can install the package and run `sigmap-bridge demo` for a checksum-
verified, zero-credit historical replay. It makes no Codex, SigMap, Git, or
network calls. A separate `doctor` command diagnoses live prerequisites, while
`submission validate` prevents incomplete external metadata from being called
ready.

## Accomplishments

- 18 retained attempts and 18 unique Codex threads: 9 raw, 9 SigMap.
- 18/18 bridge-owned worktrees reported cleaned.
- Strict versioned tasks reject shell command strings and dirty baselines.
- Independent scoring deliberately contains no SigMap context ground truth.
- Bridge Audit Log uses a SHA-256 chain plus atomic head checkpoint.
- Zero-credit replay is byte-linked to report SHA-256
  `689698a2525cb77142a3aae33295ef6d7de18a6d0bb848c85546f70c61acf490`.
- CI tests macOS and Linux across CPython 3.10–3.14.

## How Codex was used

Codex built the staged bridge contracts, isolation and audit mechanisms,
benchmark schemas and scorers, paired runner, retained benchmark evidence,
judge CLI, diagnostics, and submission gates. The collaboration produced real
course corrections: a broken Codex launcher was distinguished from missing
authentication, Apple Python 3.9 was replaced with a supported interpreter,
SigMap context delivery was corrected to read the generated payload, and
worktree cleanup stayed scoped after a sandbox permission failure.

## How GPT-5.6 was used

In Codex session `019f75cb-5dfc-7f03-a9c1-94f86dd92c8c`, GPT-5.6 added a
fail-closed provenance check to the submission validator. The validator now
cross-checks the `/feedback` UUID, requires the `GPT-5.6` model label, preserves
a precise contribution statement and safe argument-array verification command,
and rejects missing or repository-escaping changed-file paths. Contract tests
cover each rejection path. The same session produced the synchronized README,
Devpost copy, and sub-three-minute demo plan.

## Judge testing instructions

Supported platforms are macOS and Linux with CPython 3.10 through 3.14. From a
clean checkout, run `python -m pip install .`, then `sigmap-bridge demo`. The
demo is a checksum-verified, zero-credit replay that requires no Codex or SigMap
authentication, model credits, test account, or network access. Run
`sigmap-bridge submission validate submission/build-week-2026.json` to inspect
the evidence and GPT-5.6 provenance checks.

The public video URL must still be entered before final submission. Do not call
the candidate ready while the validator reports `BLOCKED`.
