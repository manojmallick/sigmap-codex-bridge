# ADR 0001: Inject SigMap context through Codex stdin

- Status: Accepted
- Date: 2026-07-18
- Issue: [#1](https://github.com/manojmallick/sigmap-codex-bridge/issues/1)

## Context

The initial product plan proposed writing SigMap output to a temporary Markdown
file and passing that file to `codex exec` with a `--context-file` option. That
option is not part of the verified Codex CLI contract used for this project.
Building around it would make the first implementation depend on an unsupported
assumption.

Codex supports a pipeline-friendly contract in which the task instruction is
passed as the `codex exec` prompt argument and piped stdin is treated as
additional context. Codex also supports `--json`, which emits a JSON Lines event
stream suitable for capturing the thread identifier, activity, completion
state, file changes, and token usage.

## Decision

The bridge will:

1. Retrieve ranked context from SigMap without modifying the target task.
2. Pass the task as the `codex exec` prompt argument.
3. Pass the retrieved context through stdin as additional context.
4. invoke `codex exec --json` and parse its JSONL event stream.
5. Select an explicit Codex sandbox policy rather than relying on an implicit
   default.
6. Record whether SigMap context was actually supplied. A missing index,
   missing executable, timeout, or retrieval failure must never be reported as
   a grounded run.

Conceptually, the process boundary is:

```text
SigMap ranked context ──stdin──> codex exec --json "<task>"
                                      │
                                      └──> JSONL events and final repository diff
```

The implementation will pass arguments as a process argument list and context
as stdin. It will not interpolate task or context text into a shell command.

## Consequences

### Positive

- The integration uses a documented, pipeline-oriented Codex interface.
- No temporary primer file is required for the normal execution path.
- JSONL provides machine-readable provenance and usage data for later A/B
  reports.
- Separating the task from context makes the two benchmark conditions easier
  to keep identical.

### Negative

- The bridge must parse and validate a streamed event format.
- Large context payloads require explicit size limits and timeout handling in a
  later version.
- Codex and SigMap CLI contracts can evolve, so contract tests and clear
  version diagnostics are required before the bridge is considered stable.

## Alternatives considered

### Temporary context file plus `--context-file`

Rejected because the proposed flag was not established as a supported Codex
CLI option. It would also introduce temporary-file cleanup and leakage risks.

### Embed context into the task prompt

Rejected because it mixes the experimental task with the treatment context,
makes exact prompt comparison harder, and increases quoting and escaping risk.

### Require MCP for the first release

Deferred. MCP may become a provider option, but requiring it would add setup
state to the initial controlled benchmark. The stdin boundary is smaller and
easier to reproduce for v0.1.0.
