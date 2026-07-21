# GPT-5.6 and Codex evidence

This file identifies the OpenAI Build Week Codex session and ties its bounded
GPT-5.6 contribution to public repository artifacts that judges can reproduce.

## Provenance

| Field | Value |
|---|---|
| Codex `/feedback` session ID | `019f75cb-5dfc-7f03-a9c1-94f86dd92c8c` |
| Session workspace | `/Users/manojmallick/Documents/sigmap-codex-bridge` |
| Session purpose | Verify GPT-5.6 contribution provenance, synchronize judge-facing evidence, and prepare the Build Week submission |
| Public repository | <https://github.com/manojmallick/sigmap-codex-bridge> |
| Devpost project | <https://devpost.com/software/sigmap-codex-bridge> |
| Public demo video | <https://www.youtube.com/watch?v=xedi5yPUlvc> |
| Submission track | Developer Tools |

The `/feedback` session ID is the competition-required provenance record. Git
history provides the public implementation trail; it does not independently
expose private model-routing metadata.

## Precise GPT-5.6 contribution

In the cited Codex session, GPT-5.6 added fail-closed, structured submission
provenance validation and synchronized the corresponding judge documentation.
The bounded implementation is public in commit `98171e3`:

- `src/sigmap_codex_bridge/submission.py` validates the declared model, matching
  `/feedback` UUID, non-empty contribution, safe argument-array verification
  command, and repository-local changed-file paths.
- `tests/test_submission.py` proves that mismatched models or sessions, shell
  command strings, missing changed files, and repository-escaping paths fail.
- `submission/build-week-2026.json` records the GPT-5.6 session, contribution,
  verification command, eight changed files, frozen report checksum, Devpost URL,
  and public video URL.
- `README.md`, `docs/submission/devpost-submission.md`,
  `docs/submission/demo-script.md`, and
  `docs/submission/release-checklist.md` expose the same evidence and judge path.

The same session used SigMap-ranked repository context to locate the submission
validator and its contract tests before making the bounded change. It also prepared
the under-three-minute demo plan and synchronized the README and Devpost narrative.

This claim is intentionally narrower than “GPT-5.6 built the whole project.” Codex
was used throughout the staged repository history, while the contribution attributed
specifically to the cited GPT-5.6 session is the provenance and submission-evidence
work above.

## Decision trail

| Decision | Repository evidence |
|---|---|
| Require the metadata model label to be exactly `GPT-5.6` | `_codex_evidence` checks in `src/sigmap_codex_bridge/submission.py` and mismatch tests |
| Cross-check the public `/feedback` UUID instead of accepting unrelated session text | `submission/build-week-2026.json` plus session-mismatch tests |
| Reject shell command strings in provenance metadata | Safe argument-array validation and unsafe-command contract tests |
| Reject missing or repository-escaping changed-file paths | Repository-local path resolution and escaped-path tests |
| Separate evidence integrity from external submission readiness | `SubmissionResult.valid`, `SubmissionResult.submission_ready`, and `--require-ready` |
| Keep measured numbers tied to frozen bytes | Report SHA-256 `689698a2525cb77142a3aae33295ef6d7de18a6d0bb848c85546f70c61acf490` |
| Never present historical replay as a fresh model run | `sigmap-bridge demo` labels itself zero-credit and reports zero live calls |
| Preserve negative results and avoid a general performance claim | The `artifact-run-status` task remains visible with higher median SigMap input |

## Public commit checkpoints

| Capability | Commit |
|---|---|
| Honest package and architecture baseline | `d2dbdc3` |
| Contract-tested bridge CLI | `56b6203` |
| Isolated worktrees and integrity model | `7da520f` |
| Strict benchmark schema and independent scoring | `7a1c06c` |
| Reproducible paired runner | `504e823` |
| Frozen 18-attempt benchmark evidence | `d7c9877` |
| Installable zero-credit replay and diagnostics | `9abdf70` |
| Submission metadata readiness gate | `a13e1dc` |
| Build Week submission candidate | `04f3871` |
| Independent replication kit definition | `218bf2a` |
| Paired analysis and regression gates | `ac07dc8` |
| Resumable execution and cost controls | `03c3ec6` |
| GPT-5.6 submission provenance validation | `98171e3` |
| Stable v1 provider, provenance, dashboard, and compatibility contracts | `dddfd15` |

## Reproduce the evidence

```bash
git clone https://github.com/manojmallick/sigmap-codex-bridge.git
cd sigmap-codex-bridge
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install .

python -m unittest tests.test_submission
sigmap-bridge submission validate \
  submission/build-week-2026.json --require-ready
sigmap-bridge demo --json
```

The validator should report:

```text
Metadata integrity: VALID
Build Week submission: READY
codex_evidence: GPT-5.6 session 019f75cb-5dfc-7f03-a9c1-94f86dd92c8c; 8 changed files
```

The demo verifies and replays the frozen 2026-07-18 report. Its output identifies
the run as `ZERO-CREDIT REPLAY — no live Codex, SigMap, Git, or network calls`.

## Measured-evidence boundary

The checked-in experiment contains 18 historical Codex attempts: three tasks, two
conditions, and three repetitions. Both raw and SigMap conditions passed 9/9
candidate test and static-check suites. The overall medians were 249.089 seconds and
766,538 input tokens raw versus 186.590 seconds and 562,358 input tokens with SigMap.

These values describe one small repository experiment. They are not a general
correctness, productivity, or model-quality claim. One task used more median input
with SigMap, and that negative result remains in the report. No independent external
replication result is claimed.

## Runtime disclosure

SigMap Codex Bridge does not call the OpenAI API directly or read an OpenAI API key.
Opt-in live bridge and benchmark commands invoke the locally installed, authenticated
Codex CLI and may consume model credits. SigMap context retrieval is performed by the
local SigMap CLI.

The judge-facing `sigmap-bridge demo` command is different: it makes no Codex,
SigMap, Git, or network calls and consumes no model credits. The competition
contribution cited here is GPT-5.6's use inside the identified Codex session to build
the provenance and submission-evidence path—not a claim that the packaged replay is
a live GPT-5.6 response.
