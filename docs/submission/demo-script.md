# Build Week demo script — 2:40 target

This script opens on the result, stays under three minutes, and never presents
the zero-credit replay as a fresh live benchmark. Rehearse commands from a clean
checkout with the wheel already installed.

## 0:00–0:15 — Result first

On screen: README measured-results table.

Narration:

> Codex passed 9/9 checks in both conditions. With SigMap-ranked context,
> median runtime was 186.590 instead of 249.089 seconds, and median total input
> was 562,358 instead of 766,538 tokens. This is a small paired efficiency
> result, not a general model-quality claim.

## 0:15–0:40 — No-rebuild judge path

```bash
cd /tmp
sigmap-bridge demo
```

Hold the first line on screen: “ZERO-CREDIT REPLAY — no live Codex, SigMap,
Git, or network calls.” Explain that the installed wheel verifies the frozen
report checksum before replaying 18 historical artifacts.

## 0:40–1:10 — Isolation and fail-closed context

On screen: the “One bridge run” diagram in `docs/submission/architecture.md`.

Narration:

> Every condition starts from the same resolved commit in its own detached Git
> worktree. Missing, empty, failed, or timed-out SigMap context fails closed;
> it never silently becomes a raw success. Cleanup targets only the
> bridge-owned, Git-recognized lease.

## 1:10–1:35 — Independent correctness

```bash
sigmap-bridge benchmark validate benchmarks/tasks/artifact-run-status.yaml --json
```

Show the argument-array test command and expected files. Explain that retrieved
context is excluded from the scoring contract; tests and observable outputs
decide correctness.

## 1:35–1:55 — Usage and the negative result

Return to the table. Point out that task 1 used *more* input with SigMap:
606,285 versus 534,456 tokens. State that all attempts—including this negative
efficiency result—remain in the report.

## 1:55–2:15 — Audit verification

Use the audit from the recorded live bridge session:

```bash
sigmap-bridge verify --audit-log "$LIVE_AUDIT_PATH" --json
```

Show `valid: true`, entry count, and head hash. Explain that the chain plus
atomic checkpoint detects ordinary modification, insertion, reordering, and
tail deletion. Do not use a fabricated path or claim external attestation.

## 2:15–2:30 — Submission integrity

```bash
sigmap-bridge submission validate submission/build-week-2026.json
```

Before external metadata is entered, show that evidence integrity is valid but
submission status is blocked. For the final recording, the same command must
show `READY` after the real `/feedback`, video, and Devpost values are supplied.

## 2:30–2:40 — Close

> SigMap Codex Bridge makes the comparison reproducible, the scoring
> independent, and the evidence inspectable. Codex does not have to guess which
> files matter—and the repository preserves the cases where that did not help.

Recording checks: total runtime no more than 2:50; result visible in the first
15 seconds; result table held for at least four seconds; terminal font legible;
no credentials, local usernames, or unrelated windows visible.
