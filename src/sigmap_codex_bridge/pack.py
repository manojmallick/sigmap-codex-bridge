"""Portable, integrity-checked benchmark pack workflows."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import tarfile
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

import yaml

from .benchmark import BenchmarkTask, BenchmarkValidationError, load_benchmark_task
from .experiment import BenchmarkRunArtifact, PairedBenchmarkRunner
from .git import GitError, GitRepository
from .preflight import PreflightResult, preflight_task
from .process import run_process


PACK_SCHEMA_VERSION = 1
EVIDENCE_INDEX_SCHEMA_VERSION = 1
SUPPORTED_SCHEMAS = {"task": 1, "artifact": 1, "report": 1}
PACK_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
REVISION_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
LICENSE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]{1,63}$")


class PackValidationError(ValueError):
    """Raised when a benchmark pack cannot be trusted or executed safely."""


@dataclass(frozen=True)
class PackTask:
    path: str
    sha256: str


@dataclass(frozen=True)
class PackEnvironment:
    python: str
    platforms: tuple[str, ...]
    setup_command: tuple[str, ...] | None


@dataclass(frozen=True)
class PackRunner:
    repetitions: int
    sandbox: str
    start_condition: str


@dataclass(frozen=True)
class BenchmarkPack:
    schema_version: int
    pack_id: str
    evidence_kind: str
    repository_url: str
    revision: str
    license: str
    public_repository: bool
    tasks: tuple[PackTask, ...]
    environment: PackEnvironment
    runner: PackRunner
    schemas: Mapping[str, int]
    manifest_path: str
    manifest_sha256: str

    def provenance(self) -> dict[str, object]:
        return {
            "pack_schema_version": self.schema_version,
            "pack_id": self.pack_id,
            "evidence_kind": self.evidence_kind,
            "manifest_sha256": self.manifest_sha256,
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _task_id(path: str) -> str:
    label = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(path).stem).strip("-")
    return label[:64] or "task"


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PackValidationError(f"{field} must be a non-empty string")
    return value


def _strict(value: object, field: str, required: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PackValidationError(f"{field} must be an object")
    fields = set(value)
    missing = sorted(required - fields)
    unknown = sorted(fields - required)
    if missing:
        raise PackValidationError(f"{field} missing fields: {', '.join(missing)}")
    if unknown:
        raise PackValidationError(f"{field} unknown fields: {', '.join(unknown)}")
    return value


def _command(value: object, field: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        raise PackValidationError(
            f"{field} must be an argument array, not a shell command string"
        )
    if not isinstance(value, Sequence) or not value:
        raise PackValidationError(f"{field} must be a non-empty argument array")
    return tuple(_text(item, f"{field} item") for item in value)


def _safe_relative(value: object, field: str) -> str:
    text = _text(value, field)
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise PackValidationError(f"{field} must be a safe repository-relative path")
    return path.as_posix()


def _inside(root: Path, relative: str, field: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise PackValidationError(f"{field} escapes the pack directory") from error
    return path


def _load_document(path: Path) -> tuple[Mapping[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise PackValidationError(f"cannot read pack manifest: {error}") from error
    try:
        if path.suffix.lower() == ".json":
            value = json.loads(raw)
        elif path.suffix.lower() in {".yaml", ".yml"}:
            value = yaml.safe_load(raw)
        else:
            raise PackValidationError("pack manifest must use .json, .yaml, or .yml")
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        raise PackValidationError(f"cannot parse pack manifest: {error}") from error
    if not isinstance(value, Mapping):
        raise PackValidationError("pack manifest must be an object")
    return value, raw


def load_benchmark_pack(path: str | Path) -> BenchmarkPack:
    """Load and fully validate a portable benchmark pack manifest."""

    manifest = Path(path).resolve()
    root = manifest.parent
    value, raw = _load_document(manifest)
    value = _strict(
        value,
        "pack",
        {
            "pack_schema_version",
            "pack_id",
            "evidence_kind",
            "repository",
            "tasks",
            "environment",
            "runner",
            "schemas",
        },
    )
    version = value["pack_schema_version"]
    if version != PACK_SCHEMA_VERSION or isinstance(version, bool):
        raise PackValidationError(
            f"unsupported pack_schema_version {version!r}; expected {PACK_SCHEMA_VERSION}"
        )
    pack_id = _text(value["pack_id"], "pack_id")
    if not PACK_ID_PATTERN.fullmatch(pack_id):
        raise PackValidationError("pack_id must be a 3-64 character lowercase slug")
    evidence_kind = _text(value["evidence_kind"], "evidence_kind")
    if evidence_kind not in {"original", "replication"}:
        raise PackValidationError("evidence_kind must be original or replication")

    repository = _strict(
        value["repository"], "repository", {"url", "revision", "license", "public"}
    )
    repository_url = _text(repository["url"], "repository.url")
    parsed_url = urlparse(repository_url)
    if parsed_url.scheme not in {"https", "file"}:
        raise PackValidationError("repository.url must use https or file")
    public = repository["public"]
    if not isinstance(public, bool):
        raise PackValidationError("repository.public must be a boolean")
    if public and (parsed_url.scheme != "https" or not parsed_url.netloc):
        raise PackValidationError("public repositories must use an HTTPS URL")
    revision = _text(repository["revision"], "repository.revision").lower()
    if not REVISION_PATTERN.fullmatch(revision):
        raise PackValidationError("repository.revision must be a full immutable commit ID")
    license_id = _text(repository["license"], "repository.license")
    if (
        not LICENSE_PATTERN.fullmatch(license_id)
        or license_id.upper() in {"UNKNOWN", "NOASSERTION", "NONE"}
    ):
        raise PackValidationError("repository.license must be a declared SPDX identifier")

    tasks_value = value["tasks"]
    if not isinstance(tasks_value, Sequence) or isinstance(tasks_value, (str, bytes)):
        raise PackValidationError("tasks must be a non-empty array")
    if not tasks_value:
        raise PackValidationError("tasks must be a non-empty array")
    tasks: list[PackTask] = []
    for index, item in enumerate(tasks_value):
        entry = _strict(item, f"tasks[{index}]", {"path", "sha256"})
        task_path = _safe_relative(entry["path"], f"tasks[{index}].path")
        task_hash = _text(entry["sha256"], f"tasks[{index}].sha256")
        if not HASH_PATTERN.fullmatch(task_hash):
            raise PackValidationError(f"tasks[{index}].sha256 must be lowercase SHA-256")
        tasks.append(PackTask(task_path, task_hash))
    paths = [task.path for task in tasks]
    if len(paths) != len(set(paths)):
        raise PackValidationError("tasks must not contain duplicate paths")
    task_ids = [_task_id(task.path) for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise PackValidationError("task paths must produce unique artifact task IDs")

    environment = _strict(
        value["environment"],
        "environment",
        {"python", "platforms", "setup_command"},
    )
    python = _text(environment["python"], "environment.python")
    platforms_value = environment["platforms"]
    if not isinstance(platforms_value, Sequence) or isinstance(
        platforms_value, (str, bytes)
    ):
        raise PackValidationError("environment.platforms must be an array")
    platforms = tuple(_text(item, "environment.platforms item") for item in platforms_value)
    if not platforms or len(platforms) != len(set(platforms)):
        raise PackValidationError("environment.platforms must be non-empty and unique")
    if any(item not in {"darwin", "linux"} for item in platforms):
        raise PackValidationError("environment.platforms supports only darwin and linux")
    setup = _command(environment["setup_command"], "environment.setup_command")

    runner = _strict(
        value["runner"], "runner", {"repetitions", "sandbox", "start_condition"}
    )
    repetitions = runner["repetitions"]
    if not isinstance(repetitions, int) or isinstance(repetitions, bool) or repetitions < 1:
        raise PackValidationError("runner.repetitions must be a positive integer")
    sandbox = _text(runner["sandbox"], "runner.sandbox")
    if sandbox not in {"read-only", "workspace-write", "danger-full-access"}:
        raise PackValidationError("runner.sandbox is unsupported")
    start_condition = _text(runner["start_condition"], "runner.start_condition")
    if start_condition not in {"raw", "sigmap"}:
        raise PackValidationError("runner.start_condition must be raw or sigmap")

    schemas = _strict(value["schemas"], "schemas", set(SUPPORTED_SCHEMAS))
    if dict(schemas) != SUPPORTED_SCHEMAS:
        raise PackValidationError(f"schemas must exactly match {SUPPORTED_SCHEMAS}")

    for task in tasks:
        task_file = _inside(root, task.path, f"task {task.path}")
        if not task_file.is_file():
            raise PackValidationError(f"task file does not exist: {task.path}")
        actual_hash = _sha256(task_file.read_bytes())
        if actual_hash != task.sha256:
            raise PackValidationError(f"task SHA-256 drift: {task.path}")
        try:
            benchmark_task = load_benchmark_task(task_file)
        except BenchmarkValidationError as error:
            raise PackValidationError(f"invalid task {task.path}: {error}") from error
        if benchmark_task.revision.lower() != revision:
            raise PackValidationError(f"task revision differs from pack: {task.path}")
        if benchmark_task.repetitions != repetitions:
            raise PackValidationError(f"task repetitions differ from pack: {task.path}")

    return BenchmarkPack(
        schema_version=PACK_SCHEMA_VERSION,
        pack_id=pack_id,
        evidence_kind=evidence_kind,
        repository_url=repository_url,
        revision=revision,
        license=license_id,
        public_repository=public,
        tasks=tuple(tasks),
        environment=PackEnvironment(python, platforms, setup),
        runner=PackRunner(repetitions, sandbox, start_condition),
        schemas=dict(schemas),
        manifest_path=str(manifest),
        manifest_sha256=_sha256(raw),
    )


def initialize_pack(
    output: str | Path,
    *,
    pack_id: str,
    evidence_kind: str,
    repository_url: str,
    revision: str,
    license_id: str,
    task_paths: Sequence[str | Path],
    python: str,
    platforms: Sequence[str],
    setup_command: Sequence[str] | None,
    repetitions: int,
    sandbox: str,
) -> BenchmarkPack:
    destination = Path(output).resolve()
    root = destination.parent
    tasks = []
    for task_value in task_paths:
        task_path = Path(task_value).resolve()
        try:
            relative = task_path.relative_to(root).as_posix()
        except ValueError as error:
            raise PackValidationError("init task files must be inside the pack directory") from error
        tasks.append({"path": relative, "sha256": _sha256(task_path.read_bytes())})
    payload = {
        "pack_schema_version": PACK_SCHEMA_VERSION,
        "pack_id": pack_id,
        "evidence_kind": evidence_kind,
        "repository": {
            "url": repository_url,
            "revision": revision,
            "license": license_id,
            "public": urlparse(repository_url).scheme == "https",
        },
        "tasks": tasks,
        "environment": {
            "python": python,
            "platforms": list(platforms),
            "setup_command": list(setup_command) if setup_command else None,
        },
        "runner": {
            "repetitions": repetitions,
            "sandbox": sandbox,
            "start_condition": "raw",
        },
        "schemas": dict(SUPPORTED_SCHEMAS),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise PackValidationError(f"refusing to overwrite existing manifest: {destination}")
    _atomic_bytes(destination, yaml.safe_dump(payload, sort_keys=False).encode("utf-8"))
    return load_benchmark_pack(destination)


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def export_pack(pack: BenchmarkPack, output: str | Path) -> dict[str, object]:
    root = Path(pack.manifest_path).parent
    files: dict[str, bytes] = {
        Path(pack.manifest_path).name: Path(pack.manifest_path).read_bytes()
    }
    for task in pack.tasks:
        files[task.path] = _inside(root, task.path, task.path).read_bytes()
    checksums = {
        "pack_schema_version": pack.schema_version,
        "pack_id": pack.pack_id,
        "evidence_kind": pack.evidence_kind,
        "manifest_sha256": pack.manifest_sha256,
        "files": {name: _sha256(data) for name, data in sorted(files.items())},
    }
    files["PACK-CHECKSUMS.json"] = (
        json.dumps(checksums, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(f"{pack.pack_id}/{name}")
            info.size = len(data)
            info.mode = 0o644
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(data))
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", filename="", mtime=0) as stream:
        stream.write(tar_buffer.getvalue())
    destination = Path(output).resolve()
    _atomic_bytes(destination, compressed.getvalue())
    return {
        "valid": True,
        "pack_id": pack.pack_id,
        "output": str(destination),
        "sha256": _sha256(compressed.getvalue()),
        "files": sorted(files),
    }


def prepare_repository(pack: BenchmarkPack, workspace: str | Path) -> Path:
    target = Path(workspace).resolve() / pack.pack_id / "repository"
    if target.exists():
        try:
            state = GitRepository(target).inspect()
        except (GitError, OSError) as error:
            raise PackValidationError(f"existing pack repository is invalid: {error}") from error
        if state.dirty or state.base_commit.lower() != pack.revision:
            raise PackValidationError("existing pack repository is dirty or at wrong revision")
        remote = run_process(
            ("git", "-C", str(target), "remote", "get-url", "origin"),
            cwd=target,
            timeout_seconds=30,
        )
        if not remote.ok or remote.stdout.strip() != pack.repository_url:
            raise PackValidationError("existing pack repository origin differs from manifest")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    clone = run_process(
        ("git", "clone", "--no-checkout", pack.repository_url, str(target)),
        cwd=target.parent,
        timeout_seconds=300,
    )
    if not clone.ok:
        raise PackValidationError(clone.stderr.strip() or "repository clone failed")
    checkout = run_process(
        ("git", "-C", str(target), "checkout", "--detach", pack.revision),
        cwd=target,
        timeout_seconds=120,
    )
    if not checkout.ok:
        raise PackValidationError(checkout.stderr.strip() or "revision checkout failed")
    state = GitRepository(target).inspect()
    if state.dirty or state.base_commit.lower() != pack.revision:
        raise PackValidationError("prepared repository did not resolve to declared revision")
    return target


def resolved_tasks(pack: BenchmarkPack, repository: Path) -> tuple[tuple[Path, BenchmarkTask], ...]:
    root = Path(pack.manifest_path).parent
    output = []
    for entry in pack.tasks:
        task_path = _inside(root, entry.path, entry.path)
        task = load_benchmark_task(task_path)
        output.append(
            (
                task_path,
                replace(
                    task,
                    repository=str(repository),
                    revision=pack.revision,
                    repetitions=pack.runner.repetitions,
                    setup_command=pack.environment.setup_command or task.setup_command,
                ),
            )
        )
    return tuple(output)


def preflight_pack(pack: BenchmarkPack, workspace: str | Path) -> tuple[PreflightResult, ...]:
    repository = prepare_repository(pack, workspace)
    worktrees = Path(workspace).resolve() / pack.pack_id / "worktrees"
    return tuple(
        preflight_task(task, worktree_root=worktrees)
        for _task_path, task in resolved_tasks(pack, repository)
    )


def run_pack(
    pack: BenchmarkPack,
    *,
    workspace: str | Path,
    output_dir: str | Path,
    experiment_id: str,
    runner: PairedBenchmarkRunner,
    model: str | None,
    codex_command: Sequence[str] | None,
    context_timeout_seconds: float,
    exact_command: Sequence[str],
) -> tuple[BenchmarkRunArtifact, ...]:
    destination = Path(output_dir).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise PackValidationError("pack output directory must be absent or empty")
    repository = prepare_repository(pack, workspace)
    worktrees = Path(workspace).resolve() / pack.pack_id / "worktrees"
    artifacts: list[BenchmarkRunArtifact] = []
    for task_path, task in resolved_tasks(pack, repository):
        artifacts.extend(
            runner.run_task(
                task,
                task_file=task_path,
                output_dir=destination,
                experiment_id=experiment_id,
                sandbox=pack.runner.sandbox,
                model=model,
                codex_command=codex_command,
                start_condition=pack.runner.start_condition,
                context_timeout_seconds=context_timeout_seconds,
                worktree_root=worktrees,
                exact_command=exact_command,
                benchmark_pack=pack.provenance(),
            )
        )
    seal_evidence(pack, destination)
    return tuple(artifacts)


def seal_evidence(pack: BenchmarkPack, evidence_dir: str | Path) -> dict[str, object]:
    root = Path(evidence_dir).resolve()
    if not root.is_dir():
        raise PackValidationError(f"evidence directory does not exist: {root}")
    files = {
        path.relative_to(root).as_posix(): _sha256(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "evidence-index.json"
    }
    if not files:
        raise PackValidationError("cannot seal empty evidence")
    index = {
        "evidence_index_schema_version": EVIDENCE_INDEX_SCHEMA_VERSION,
        **pack.provenance(),
        "files": files,
    }
    _atomic_bytes(
        root / "evidence-index.json",
        (json.dumps(index, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return index


def verify_evidence(pack: BenchmarkPack, evidence_dir: str | Path) -> dict[str, object]:
    root = Path(evidence_dir).resolve()
    index_path = root / "evidence-index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PackValidationError(f"cannot read evidence index: {error}") from error
    if not isinstance(index, Mapping):
        raise PackValidationError("evidence index must be an object")
    expected_provenance = pack.provenance()
    if index.get("evidence_index_schema_version") != EVIDENCE_INDEX_SCHEMA_VERSION:
        raise PackValidationError("unsupported evidence index schema")
    for field, expected in expected_provenance.items():
        if index.get(field) != expected:
            raise PackValidationError(f"evidence index {field} differs from pack")
    indexed_files = index.get("files")
    if not isinstance(indexed_files, Mapping) or not indexed_files:
        raise PackValidationError("evidence index files must be a non-empty object")
    actual_files = {
        path.relative_to(root).as_posix(): _sha256(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "evidence-index.json"
    }
    if dict(indexed_files) != actual_files:
        raise PackValidationError("evidence file set or SHA-256 hashes drifted")

    artifacts: list[Mapping[str, Any]] = []
    for relative in sorted(actual_files):
        if not relative.endswith(".json") or relative == "report.json":
            continue
        try:
            value = json.loads((root / relative).read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise PackValidationError(f"invalid evidence JSON: {relative}") from error
        if isinstance(value, Mapping) and "artifact_schema_version" in value:
            artifacts.append(value)
    if not artifacts:
        raise PackValidationError("no benchmark artifacts found in evidence")

    seen_attempts: set[tuple[str, str]] = set()
    pairs: dict[tuple[str, str, int, str], set[str]] = {}
    declared_task_ids = {_task_id(task.path) for task in pack.tasks}
    for artifact in artifacts:
        if artifact.get("artifact_schema_version") != pack.schemas["artifact"]:
            raise PackValidationError("artifact schema differs from pack")
        if str(artifact.get("resolved_revision", "")).lower() != pack.revision:
            raise PackValidationError("artifact revision differs from pack")
        provenance = artifact.get("benchmark_pack")
        if provenance != expected_provenance:
            raise PackValidationError("artifact pack provenance differs or is missing")
        task_id = str(artifact.get("task_id", ""))
        if task_id not in declared_task_ids:
            raise PackValidationError(f"artifact task is not declared by pack: {task_id}")
        pair_id = str(artifact.get("pair_id", ""))
        condition = str(artifact.get("condition", ""))
        experiment_id = str(artifact.get("experiment_id", ""))
        if not pair_id or not experiment_id:
            raise PackValidationError("artifact pair_id and experiment_id must be non-empty")
        if condition not in {"raw", "sigmap"}:
            raise PackValidationError(f"artifact condition is invalid: {condition}")
        repetition_value = artifact.get("repetition")
        if (
            not isinstance(repetition_value, int)
            or isinstance(repetition_value, bool)
            or not 1 <= repetition_value <= pack.runner.repetitions
        ):
            raise PackValidationError("artifact repetition is outside the pack contract")
        attempt = (pair_id, condition)
        if attempt in seen_attempts:
            raise PackValidationError(f"duplicate artifact attempt: {pair_id} {condition}")
        seen_attempts.add(attempt)
        pair_key = (
            experiment_id,
            task_id,
            repetition_value,
            pair_id,
        )
        pairs.setdefault(pair_key, set()).add(condition)
    incomplete = [key for key, conditions in pairs.items() if conditions != {"raw", "sigmap"}]
    if incomplete:
        raise PackValidationError(f"incomplete raw/SigMap pairs: {len(incomplete)}")
    expected_pairs = len(pack.tasks) * pack.runner.repetitions
    if len(pairs) != expected_pairs:
        raise PackValidationError(
            f"evidence has {len(pairs)} pairs; expected {expected_pairs}"
        )
    return {
        "valid": True,
        "pack_id": pack.pack_id,
        "evidence_kind": pack.evidence_kind,
        "artifact_count": len(artifacts),
        "pair_count": len(pairs),
        "file_count": len(actual_files),
    }
