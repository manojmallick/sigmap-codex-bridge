# Evidence dashboard

The dashboard command regenerates a report from every supplied artifact directory and
embeds those reports in deterministic JSON and Markdown outputs:

```bash
sigmap-bridge benchmark dashboard \
  benchmarks/results/build-week-2026-07-18/artifacts \
  --json-output /tmp/dashboard.json \
  --markdown-output /tmp/dashboard.md --json
```

Each input retains its own compatibility key derived from task identifiers,
environment metadata, and benchmark-pack provenance. Inputs with different keys are
listed separately rather than averaged together. Full embedded reports retain
per-task metrics, failed attempts, incomplete-pair exclusions, uncertainty status,
and negative results.

The dashboard validates artifact and pairing contracts before writing output. It does
not prove statistical significance, general model quality, or independent
replication. Source order is explicit and output bytes are stable for identical
inputs and arguments.
