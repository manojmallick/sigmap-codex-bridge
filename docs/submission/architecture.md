# Architecture and benchmark diagrams

![SigMap Codex Bridge Architecture Diagram](../assets/architecture.png)

## One bridge run

```mermaid
flowchart LR
    U["Task + clean repository"] --> G["Resolve immutable Git HEAD"]
    G --> W["Create bridge-owned detached worktree"]
    W --> C{"Condition"}
    C -->|raw| R["Context explicitly disabled"]
    C -->|SigMap| S["Retrieve ranked repository context"]
    S -->|missing, empty, timeout, failure| F["Fail closed"]
    R --> X["Codex exec with argument-array command"]
    S --> X
    X --> T["Run candidate tests and static checks"]
    T --> D["Capture Git-visible changes and usage"]
    D --> A["Append hash-chained audit evidence"]
    A --> K["Clean only the owned worktree lease"]
```

Retrieved context guides Codex, but it is never correctness ground truth.
Correctness comes from declared tests and observable repository/process output.

## Reproducible paired A/B benchmark

```mermaid
sequenceDiagram
    participant P as Preflight
    participant O as Pair orchestrator
    participant R as Raw condition
    participant S as SigMap condition
    participant J as Independent scorer
    participant E as Evidence/report

    P->>P: Resolve revision and pass clean baseline
    loop Three repetitions
        O->>O: Alternate first condition
        O->>R: Same task, revision, model, sandbox
        R->>J: Tests, changes, runtime, usage
        O->>S: Same task, revision, model, sandbox
        S->>J: Tests, changes, runtime, usage
        J->>E: Retain both raw JSON artifacts
    end
    E->>E: Sort artifacts and regenerate byte-stable reports
```

Each repetition is a complete pair. The first condition alternates to reduce
order effects. Every artifact records the resolved revision, exact command,
environment, condition order, process outcomes, changes, independent score,
failure details, and cleanup result.

## Evidence boundaries

```mermaid
flowchart TD
    B["Fresh live benchmark"] --> H["18 immutable raw artifacts"]
    H --> M["Deterministic JSON + Markdown report"]
    M --> P["Packaged report byte copy"]
    P --> Z["Zero-credit historical replay"]
    H --> Q["Independent tests and scoring"]
    H --> L["Bridge Audit Log + atomic checkpoint"]
    L --> V["sigmap-bridge verify"]
```

The packaged replay verifies report integrity and judge usability. It cannot
create fresh evidence. The Bridge Audit Log detects ordinary insertion,
modification, deletion, and reordering, but is not an externally signed
attestation against an actor who can rewrite every local record.
