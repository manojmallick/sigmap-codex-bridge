"""Zero-credit replay of the checked-in measured benchmark report."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from typing import Any, Mapping


DEMO_SCHEMA_VERSION = 1
REPLAY_LABEL = "ZERO-CREDIT REPLAY — no live Codex, SigMap, Git, or network calls"


class DemoError(ValueError):
    """Raised when packaged replay evidence is missing or has drifted."""


def _resource_bytes(name: str) -> bytes:
    resource = files("sigmap_codex_bridge").joinpath("demo_data", name)
    try:
        return resource.read_bytes()
    except OSError as error:
        raise DemoError(f"cannot read packaged demo resource {name}: {error}") from error


def load_replay() -> tuple[dict[str, Any], dict[str, Any]]:
    """Load packaged evidence and verify its checksum."""

    try:
        manifest = json.loads(_resource_bytes("manifest.json"))
        report_bytes = _resource_bytes("report.json")
        report = json.loads(report_bytes)
    except json.JSONDecodeError as error:
        raise DemoError(f"packaged replay JSON is invalid: {error}") from error
    if not isinstance(manifest, dict) or not isinstance(report, dict):
        raise DemoError("packaged replay resources must be JSON objects")
    if manifest.get("demo_schema_version") != DEMO_SCHEMA_VERSION:
        raise DemoError("unsupported packaged demo schema")
    actual_hash = hashlib.sha256(report_bytes).hexdigest()
    if manifest.get("report_sha256") != actual_hash:
        raise DemoError("packaged replay report checksum mismatch")
    if manifest.get("source_experiment_id") not in report.get("experiment_ids", []):
        raise DemoError("packaged replay manifest and report experiment differ")
    return manifest, report


def replay_demo() -> dict[str, object]:
    """Build replay events from package data without external service calls."""

    manifest, report = load_replay()
    tasks = report.get("tasks")
    overall = report.get("overall")
    if not isinstance(tasks, Mapping) or not isinstance(overall, Mapping):
        raise DemoError("packaged replay report is missing task summaries")
    events: list[dict[str, object]] = [
        {
            "type": "replay.started",
            "label": REPLAY_LABEL,
            "experiment_id": manifest["source_experiment_id"],
        }
    ]
    for task_id, conditions in tasks.items():
        events.append(
            {
                "type": "task.replayed",
                "task_id": task_id,
                "conditions": conditions,
            }
        )
    events.append(
        {
            "type": "replay.completed",
            "artifact_count": report.get("artifact_count"),
            "overall": overall,
            "comparisons": report.get("comparisons"),
            "failures": report.get("failures"),
        }
    )
    return {
        "demo_schema_version": DEMO_SCHEMA_VERSION,
        "mode": "replay",
        "replay": True,
        "label": REPLAY_LABEL,
        "live_calls": 0,
        "credits_required": False,
        "source": {
            "experiment_id": manifest["source_experiment_id"],
            "revision": manifest["source_revision"],
            "report_commit": manifest["source_report_commit"],
            "report_path": manifest["source_report_path"],
            "report_sha256": manifest["report_sha256"],
        },
        "events": events,
        "report": report,
    }


def render_replay(payload: Mapping[str, object]) -> str:
    """Render a concise judge-facing replay without implying a live run."""

    report = payload["report"]
    assert isinstance(report, Mapping)
    overall = report["overall"]
    tasks = report["tasks"]
    assert isinstance(overall, Mapping)
    assert isinstance(tasks, Mapping)
    lines = [
        str(payload["label"]),
        f"Source experiment: {payload['source']['experiment_id']}",  # type: ignore[index]
        f"Artifacts replayed: {report['artifact_count']}",
        "",
    ]
    for task_id, conditions in tasks.items():
        assert isinstance(conditions, Mapping)
        raw = conditions["raw"]
        sigmap = conditions["sigmap"]
        assert isinstance(raw, Mapping)
        assert isinstance(sigmap, Mapping)
        lines.append(
            f"{task_id}: raw {raw['passed']}/{raw['attempts']} at "
            f"{raw['medians']['runtime_seconds']:.3f}s; "  # type: ignore[index]
            f"SigMap {sigmap['passed']}/{sigmap['attempts']} at "
            f"{sigmap['medians']['runtime_seconds']:.3f}s"  # type: ignore[index]
        )
    raw = overall["raw"]
    sigmap = overall["sigmap"]
    assert isinstance(raw, Mapping)
    assert isinstance(sigmap, Mapping)
    lines.extend(
        (
            "",
            f"Overall: raw {raw['passed']}/{raw['attempts']}, "
            f"SigMap {sigmap['passed']}/{sigmap['attempts']}",
            f"Median runtime: raw {raw['medians']['runtime_seconds']:.3f}s, "  # type: ignore[index]
            f"SigMap {sigmap['medians']['runtime_seconds']:.3f}s",  # type: ignore[index]
            "Replay complete. Live calls made: 0.",
        )
    )
    return "\n".join(lines)
