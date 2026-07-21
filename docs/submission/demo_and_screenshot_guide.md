# SigMap Codex Bridge — Demo & Screenshot Guide

This guide provides step-by-step instructions for performing the live video demo and taking screenshots for your **SigMap Codex Bridge** submission (OpenAI Build Week 2026).

---

## 🖼️ Architecture Diagram PNG

The high-resolution architecture diagram PNG has been generated and saved to:
- [`docs/assets/architecture.png`](file:///Users/manojmallick/Documents/sigmap-codex-bridge/docs/assets/architecture.png)
- [`docs/submission/architecture.png`](file:///Users/manojmallick/Documents/sigmap-codex-bridge/docs/submission/architecture.png)
- [`architecture.png`](file:///Users/manojmallick/Documents/sigmap-codex-bridge/architecture.png)

---

## 🎬 Step-by-Step Demo Script & Narration (Target: 2:45)

### Phase 0: 0:00–0:15 — The Idea & Problem Hook
- **On Screen**: [`README.md`](file:///Users/manojmallick/Documents/sigmap-codex-bridge/README.md) Title, Badges & "Why SigMap Codex Bridge" section.
- **Narration**:
  > *"Context retrieval tools are easy to demo but hard to evaluate: model runs drift, favorable runs get over-selected, and missing context can masquerade as success. SigMap Codex Bridge runs Codex in paired raw versus SigMap-ranked conditions from the same commit in isolated worktrees to measure real impact."*
- **📸 Screenshot #0**: Repository README Header & Problem/Solution Matrix.

---

### Phase 1: 0:15–0:30 — Result First (Measured Evidence)
- **On Screen**: [`README.md`](file:///Users/manojmallick/Documents/sigmap-codex-bridge/README.md) Measured Build Week Results Table.
- **Narration**:
  > *"Codex passed 9/9 checks in both conditions. With SigMap-ranked context, median runtime dropped from 249 to 186 seconds—a 25% speedup—and input tokens dropped from 766k to 562k. This is a small paired efficiency result, retained with zero cherry-picking."*
- **📸 Screenshot #1**: Measured Build Week Results table from `README.md`.

---

### Phase 2: 0:30–0:55 — Zero-Credit Judge Path
- **CLI Command to Run**:
  ```bash
  # Run directly from repository root:
  ./sigmap-bridge demo

  # Or if installed in virtualenv:
  cd /tmp && sigmap-bridge demo
  ```
- **On Screen**: Terminal output showing `ZERO-CREDIT REPLAY — no live Codex, SigMap, Git, or network calls.`
- **Narration**:
  > *"The CLI replays all 18 historical attempts with zero model credits or network calls. Judges can instantly verify frozen report checksums and raw artifacts locally."*
- **📸 Screenshot #2**: Terminal output of `./sigmap-bridge demo`.

---

### Phase 3: 0:55–1:20 — Worktree Isolation & Architecture
- **On Screen**: [`docs/assets/architecture.png`](file:///Users/manojmallick/Documents/sigmap-codex-bridge/docs/assets/architecture.png) (System Architecture diagram).
- **Narration**:
  > *"Every condition starts from the same resolved commit in its own detached Git worktree. Missing, empty, or failed SigMap context fails closed—it never silently becomes a raw success. Cleanup targets only the bridge-owned lease."*
- **📸 Screenshot #3**: Architecture diagram in `docs/assets/architecture.png`.

---

### Phase 4: 1:05–1:30 — Task Validation & Independent Correctness
- **CLI Command to Run**:
  ```bash
  sigmap-bridge benchmark validate benchmarks/tasks/artifact-run-status.yaml --json
  ```
- **On Screen**: JSON validation output confirming schema integrity.
- **Narration**:
  > *"Retrieved context is excluded from the scoring contract; tests and observable outputs decide correctness independently."*
- **📸 Screenshot #4**: JSON output of `benchmark validate`.

---

### Phase 5: 1:30–1:50 — Environment Readiness Check
- **CLI Command to Run**:
  ```bash
  ./sigmap-bridge doctor --repo .
  ```
- **On Screen**: `doctor` diagnostic output verifying Git, Codex, and SigMap availability.
- **Narration**:
  > *"The doctor command verifies local environment readiness before a live run. It checks Python version bounds, Git repository hygiene, Codex authentication, and SigMap index status without running a full benchmark."*
- **📸 Screenshot #5**: Terminal output of `sigmap-bridge doctor`.

---

### Phase 6: 1:50–2:15 — Codex and GPT-5.6 Contribution (One-Off Bridge Run)
- **CLI Command to Run**:
  ```bash
  # Fast live demo (9 seconds, inspects pyproject.toml and cleans worktree):
  ./sigmap-bridge run "Read pyproject.toml and report its version" --repo . --json
  ```
- **On Screen**: README "Built with Codex and GPT-5.6" table & bridge result JSON showing execution status and audit hash.
- **Narration**:
  > *"Codex accelerated implementation, testing, and repository navigation across the project. In the cited GPT-5.6 session, it added structured submission provenance: the validator cross-checks the feedback UUID, model label, contribution, safe verification command, and changed files. The contract tests prove those checks fail closed."*
- **📸 Screenshot #6**: JSON result of `sigmap-bridge run`.

---

### Phase 7: 2:15–2:30 — Submission Metadata & Verification
- **CLI Command to Run**:
  ```bash
  ./sigmap-bridge submission validate submission/build-week-2026.json
  ```
- **On Screen**: `Metadata integrity: VALID` along with `codex_evidence` GPT-5.6 session details.
- **Narration**:
  > *"Running submission validate checks machine-readable submission evidence. It verifies the report checksum, Codex feedback session, and flags any missing external URLs like the final video link."*
- **📸 Screenshot #7**: Terminal output of `submission validate`.

---

### Phase 8: 2:30–2:45 — Close & Summary
- **On Screen**: README Summary / Closing screen.
- **Narration**:
  > *"SigMap Codex Bridge makes the comparison reproducible, the scoring independent, and the evidence inspectable. Codex does not have to guess which files matter—and the repository preserves the cases where that did not help."*

---

## 📋 Captured Screenshots & Devpost Assets

| # | Screenshot Asset | Command / Asset Displayed | Description |
|---|---|---|---|
| 1 | [`docs/assets/architecture.png`](file:///Users/manojmallick/Documents/sigmap-codex-bridge/docs/assets/architecture.png) | System Flowchart | Visual system architecture & fail-closed Git worktree isolation |
| 2 | [`docs/assets/demo-replay-cli.png`](file:///Users/manojmallick/Documents/sigmap-codex-bridge/docs/assets/demo-replay-cli.png) | `./sigmap-bridge demo` | Zero-credit offline judge replay output |
| 3 | [`docs/assets/doctor-cli.png`](file:///Users/manojmallick/Documents/sigmap-codex-bridge/docs/assets/doctor-cli.png) | `./sigmap-bridge doctor --repo .` | Live readiness & zero-credit diagnostic status |
| 4 | [`docs/assets/benchmark-validate-cli.png`](file:///Users/manojmallick/Documents/sigmap-codex-bridge/docs/assets/benchmark-validate-cli.png) | `./sigmap-bridge benchmark validate ... --json` | Strict schema-v1 benchmark task JSON validation |
| 5 | [`docs/assets/submission-validate-cli.png`](file:///Users/manojmallick/Documents/sigmap-codex-bridge/docs/assets/submission-validate-cli.png) | `./sigmap-bridge submission validate ...` | Submission integrity & GPT-5.6 Codex evidence validation |

---

## 🛠️ Complete CLI Options Reference

All CLI commands and options are documented in [`README.md`](file:///Users/manojmallick/Documents/sigmap-codex-bridge/README.md#detailed-cli-options--subcommands-reference).

### Common Global & Command Options:
- `--repo PATH`: Target Git repository path (default: `.`)
- `--sandbox {read-only,workspace-write,danger-full-access}`: Codex sandbox policy
- `--json`: Format output as structured JSON
- `--no-sigmap`: Force raw condition without context retrieval
- `--worktree-root PATH`: Custom path for detached Git worktrees
- `--audit-log PATH`: Custom path for SHA-256 audit log
- `--require-live`: Require live model and indexing readiness in `doctor`
- `--require-ready`: Require complete video & external URL readiness in `submission validate`
- `--experiment-id ID`: Unique identifier for paired benchmark runs
- `--state-file PATH`: Atomic JSON state file path enabling resumable execution
- `--max-workers N`: Concurrent pair execution threads (1–32)
- `--max-pairs N`: Budget cap on total completed pairs
- `--max-runtime-seconds N`: Budget cap on total execution time in seconds
- `--max-total-tokens N`: Budget cap on total tokens consumed
