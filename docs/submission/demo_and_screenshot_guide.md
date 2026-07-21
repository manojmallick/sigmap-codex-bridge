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

### Phase 1: 0:00–0:15 — Result First
- **On Screen**: [`README.md`](file:///Users/manojmallick/Documents/sigmap-codex-bridge/README.md) Measured Results Table.
- **Narration**:
  > *"Codex passed 9/9 checks in both conditions. With SigMap-ranked context, median runtime was 186.590 instead of 249.089 seconds, and median total input was 562,358 instead of 766,538 tokens. This is a small paired efficiency result, not a general model-quality claim."*
- **📸 Screenshot #1**: Capture the Measured Build Week Results table from `README.md`.

---

### Phase 2: 0:15–0:40 — Zero-Credit Judge Path
- **CLI Command to Run**:
  ```bash
  # Run directly from repository root:
  ./sigmap-bridge demo

  # Or if installed in virtualenv:
  cd /tmp && sigmap-bridge demo
  ```
- **On Screen**: Terminal output showing:
  `ZERO-CREDIT REPLAY — no live Codex, SigMap, Git, or network calls.`
- **Narration**:
  > *"The installed wheel verifies the frozen report checksum before replaying 18 historical artifacts. Judges can run this without consuming model credits."*
- **📸 Screenshot #2**: Terminal output of `sigmap-bridge demo`.

---

### Phase 3: 0:40–1:05 — Isolation & Architecture
- **On Screen**: [`docs/assets/architecture.png`](file:///Users/manojmallick/Documents/sigmap-codex-bridge/docs/assets/architecture.png) (System Architecture diagram).
- **Narration**:
  > *"Every condition starts from the same resolved commit in its own detached Git worktree. Missing, empty, failed, or timed-out SigMap context fails closed; it never silently becomes a raw success. Cleanup targets only the bridge-owned, Git-recognized lease."*
- **📸 Screenshot #3**: Architecture diagram viewed in browser or image viewer.

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
  sigmap-bridge doctor --repo .
  ```
- **On Screen**: `doctor` diagnostic output verifying Git, Codex, and SigMap availability.
- **📸 Screenshot #5**: Terminal output of `sigmap-bridge doctor`.

---

### Phase 6: 1:50–2:15 — One-Off Bridge Run (Live / Demonstration)
- **CLI Command to Run**:
  ```bash
  sigmap-bridge run "Fix the JWT validation bug and run tests" --repo . --json
  ```
- **On Screen**: Bridge result JSON showing requested context, execution status, and audit hash.
- **📸 Screenshot #6**: JSON result of `sigmap-bridge run`.

---

### Phase 7: 2:15–2:45 — Submission Metadata & Verification
- **CLI Command to Run**:
  ```bash
  sigmap-bridge submission validate submission/build-week-2026.json
  ```
- **On Screen**: `Metadata integrity: VALID` along with `codex_evidence` GPT-5.6 session details.
- **📸 Screenshot #7**: Terminal output of `submission validate`.

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
