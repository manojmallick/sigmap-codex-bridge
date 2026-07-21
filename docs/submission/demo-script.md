# Build Week demo script — 2:45 target

This script opens on the result, stays under three minutes, and never presents
the zero-credit replay as a fresh live benchmark. Rehearse commands from a clean
checkout with the wheel already installed.

## 0:00–0:15 — The Problem & Idea (Hook)

On screen: README title, badges, and "Why SigMap Codex Bridge" table.

Narration:

> Context retrieval tools are easy to demo but hard to evaluate: model runs drift,
> favorable runs get over-selected, and missing context can masquerade as success.
> SigMap Codex Bridge runs Codex in paired raw versus SigMap-ranked conditions
> from the same commit in isolated worktrees to measure real impact.

## 0:15–0:30 — Result first

On screen: README measured-results table.

Narration:

> Codex passed 9/9 checks in both conditions. With SigMap-ranked context,
> median runtime was 186.590 instead of 249.089 seconds, and median total input
> was 562,358 instead of 766,538 tokens. This is a small paired efficiency
> result, not a general model-quality claim.

## 0:30–0:55 — Zero-credit judge path

```bash
# Run directly from the repository checkout:
./sigmap-bridge demo

# Or from outside after installing into venv (pip install -e .):
cd /tmp && sigmap-bridge demo
```

Hold the first line on screen: “ZERO-CREDIT REPLAY — no live Codex, SigMap,
Git, or network calls.” Explain that the installed wheel verifies the frozen
report checksum before replaying 18 historical artifacts.

## 0:55–1:20 — Isolation and fail-closed context

On screen: the “One bridge run” diagram in `docs/submission/architecture.md`.

Narration:

> Every condition starts from the same resolved commit in its own detached Git
> worktree. Missing, empty, failed, or timed-out SigMap context fails closed;
> it never silently becomes a raw success. Cleanup targets only the
> bridge-owned, Git-recognized lease.

## 1:20–1:40 — Independent correctness

```bash
./sigmap-bridge benchmark validate benchmarks/tasks/artifact-run-status.yaml --json
```

Show the argument-array test command and expected files. Explain that retrieved
context is excluded from the scoring contract; tests and observable outputs
decide correctness.

## 1:40–2:00 — Environment readiness check

```bash
./sigmap-bridge doctor --repo .
```

Show `Live readiness` and `Zero-credit replay` diagnostics. Explain that doctor checks
Python version bounds, Git hygiene, Codex auth, and SigMap index status without running a benchmark.

## 2:00–2:20 — Codex and GPT-5.6 contribution

On screen: README “Built with Codex and GPT-5.6” table, then the
`codex_evidence` result from the submission validator.

Narration:

> Codex accelerated implementation, testing, and repository navigation across
> the project. In the cited GPT-5.6 session, it added structured submission
> provenance: the validator cross-checks the feedback UUID, model label,
> contribution, safe verification command, and changed files. The contract
> tests prove those checks fail closed. The feedback session is the authoritative
> interaction record.

## 2:20–2:35 — Submission integrity

```bash
./sigmap-bridge submission validate submission/build-week-2026.json
```

Show `Metadata integrity: VALID`, the `codex_evidence: GPT-5.6 session ...`
line, and the single expected video-URL warning. Explain that the recording
must be uploaded before its real URL can be added. After upload, add that URL
and rerun with `--require-ready`; do not stage a fake READY result in the video.

## 2:35–2:45 — Close

> SigMap Codex Bridge makes the comparison reproducible, the scoring
> independent, and the evidence inspectable. Codex does not have to guess which
> files matter—and the repository preserves the cases where that did not help.

Recording checks: total runtime no more than 2:50; result visible in the first
15 seconds; result table held for at least four seconds; terminal font legible;
no credentials, local usernames, or unrelated windows visible.
