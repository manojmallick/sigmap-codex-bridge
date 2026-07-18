import contextlib
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import yaml

from git_helpers import initialize_repo
from sigmap_codex_bridge.cli import main
from sigmap_codex_bridge.codex import CodexRunner
from sigmap_codex_bridge.experiment import PairedBenchmarkRunner
from sigmap_codex_bridge.pack import (
    PackValidationError,
    export_pack,
    initialize_pack,
    load_benchmark_pack,
    preflight_pack,
    run_pack,
    seal_evidence,
    verify_evidence,
)
from sigmap_codex_bridge.sigmap import SigMapContextProvider


ROOT = Path(__file__).resolve().parents[1]
FAKE_CODEX = ROOT / "tests" / "fixtures" / "fake_codex.py"
FAKE_SIGMAP = ROOT / "tests" / "fixtures" / "fake_sigmap.py"
REFERENCE_PACK = ROOT / "benchmark_packs" / "pypa-sampleproject-v1" / "pack.yaml"


class BenchmarkPackTests(unittest.TestCase):
    def task(self, path: Path, revision: str, *, repetitions: int = 1) -> None:
        value = {
            "schema_version": 1,
            "repository": "$PACK_REPOSITORY",
            "revision": revision,
            "prompt": "Create the requested fixture",
            "expected_behavior": "Regression checks pass",
            "test_command": [sys.executable, "-c", "raise SystemExit(0)"],
            "allowed_files": ["codex-created.txt"],
            "expected_files": ["codex-created.txt"],
            "repetitions": repetitions,
            "timeout_seconds": 10,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")

    def manifest(
        self,
        path: Path,
        repo: Path,
        revision: str,
        task: Path,
        *,
        evidence_kind: str = "replication",
    ) -> Path:
        import hashlib

        value = {
            "pack_schema_version": 1,
            "pack_id": "fixture-pack-v1",
            "evidence_kind": evidence_kind,
            "repository": {
                "url": repo.resolve().as_uri(),
                "revision": revision,
                "license": "MIT",
                "public": False,
            },
            "tasks": [
                {
                    "path": task.relative_to(path.parent).as_posix(),
                    "sha256": hashlib.sha256(task.read_bytes()).hexdigest(),
                }
            ],
            "environment": {
                "python": ">=3.10,<3.15",
                "platforms": ["darwin", "linux"],
                "setup_command": None,
            },
            "runner": {
                "repetitions": 1,
                "sandbox": "workspace-write",
                "start_condition": "raw",
            },
            "schemas": {"task": 1, "artifact": 1, "report": 1},
        }
        path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
        return path

    def fixture(self, root: Path):
        repo = root / "source"
        revision = initialize_repo(repo)
        task = root / "pack" / "tasks" / "task.yaml"
        self.task(task, revision)
        manifest = self.manifest(root / "pack" / "pack.yaml", repo, revision, task)
        return repo, revision, task, manifest

    def runner(self) -> PairedBenchmarkRunner:
        return PairedBenchmarkRunner(
            context_provider=SigMapContextProvider(
                command=(sys.executable, str(FAKE_SIGMAP)),
                env={"FAKE_SIGMAP_MODE": "ready"},
            ),
            codex_runner_factory=lambda timeout: CodexRunner(
                command=(sys.executable, str(FAKE_CODEX)),
                timeout_seconds=timeout,
                env={"FAKE_CODEX_MODE": "write"},
            ),
        )

    def test_loads_strict_pack_and_reference_pack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _repo, revision, _task, manifest = self.fixture(Path(directory))
            pack = load_benchmark_pack(manifest)

        reference = load_benchmark_pack(REFERENCE_PACK)
        self.assertEqual(pack.revision, revision)
        self.assertEqual(pack.evidence_kind, "replication")
        self.assertEqual(reference.repository_url, "https://github.com/pypa/sampleproject.git")
        self.assertEqual(reference.license, "MIT")

    def test_rejects_unsafe_or_drifting_pack_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _repo, _revision, _task, manifest = self.fixture(root)
            original = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            cases = (
                (("repository", "revision"), "main", "immutable commit"),
                (("repository", "license"), "UNKNOWN", "SPDX"),
                (("tasks", 0, "path"), "../task.yaml", "safe repository-relative"),
                (("tasks", 0, "sha256"), "0" * 64, "SHA-256 drift"),
                (("environment", "setup_command"), "python setup.py", "argument array"),
                (("schemas", "artifact"), 2, "schemas must exactly match"),
            )
            for index, (path, value, message) in enumerate(cases):
                payload = json.loads(json.dumps(original))
                target = payload
                for part in path[:-1]:
                    target = target[part]
                target[path[-1]] = value
                candidate = manifest.parent / f"pack-{index}.json"
                candidate.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(message=message):
                    with self.assertRaisesRegex(PackValidationError, message):
                        load_benchmark_pack(candidate)

            duplicate = json.loads(json.dumps(original))
            duplicate["tasks"].append(duplicate["tasks"][0])
            duplicate_path = manifest.parent / "pack-duplicate.json"
            duplicate_path.write_text(json.dumps(duplicate), encoding="utf-8")
            with self.assertRaisesRegex(PackValidationError, "duplicate paths"):
                load_benchmark_pack(duplicate_path)

            unknown = json.loads(json.dumps(original))
            unknown["unexpected"] = True
            unknown_path = manifest.parent / "pack-unknown.json"
            unknown_path.write_text(json.dumps(unknown), encoding="utf-8")
            with self.assertRaisesRegex(PackValidationError, "unknown fields"):
                load_benchmark_pack(unknown_path)

    def test_init_and_export_are_strict_and_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "source"
            revision = initialize_repo(repo)
            task = root / "pack" / "tasks" / "task.yaml"
            self.task(task, revision)
            pack = initialize_pack(
                root / "pack" / "pack.yaml",
                pack_id="fixture-pack-v1",
                evidence_kind="replication",
                repository_url=repo.resolve().as_uri(),
                revision=revision,
                license_id="MIT",
                task_paths=(task,),
                python=">=3.10,<3.15",
                platforms=("darwin", "linux"),
                setup_command=None,
                repetitions=1,
                sandbox="workspace-write",
            )
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"
            export_pack(pack, first)
            export_pack(pack, second)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            with tarfile.open(first, "r:gz") as archive:
                names = archive.getnames()
            self.assertEqual(
                names,
                [
                    "fixture-pack-v1/PACK-CHECKSUMS.json",
                    "fixture-pack-v1/pack.yaml",
                    "fixture-pack-v1/tasks/task.yaml",
                ],
            )

    def test_preflight_clones_pinned_revision_without_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _repo, revision, _task, manifest = self.fixture(root)
            results = preflight_pack(load_benchmark_pack(manifest), root / "workspace")

            clone = root / "workspace" / "fixture-pack-v1" / "repository"
            self.assertTrue(all(result.valid for result in results))
            self.assertEqual(results[0].revision, revision)
            self.assertTrue(clone.is_dir())

    def test_pack_run_stamps_and_verifies_complete_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _repo, revision, _task, manifest = self.fixture(root)
            pack = load_benchmark_pack(manifest)
            evidence = root / "evidence"
            artifacts = run_pack(
                pack,
                workspace=root / "workspace",
                output_dir=evidence,
                experiment_id="replication-fixture",
                runner=self.runner(),
                model="fixture-model",
                codex_command=None,
                context_timeout_seconds=5,
                exact_command=("sigmap-bridge", "benchmark", "pack", "run"),
            )
            verified = verify_evidence(pack, evidence)

            self.assertEqual(len(artifacts), 2)
            self.assertEqual(verified["pair_count"], 1)
            self.assertEqual(verified["artifact_count"], 2)
            self.assertEqual({item.resolved_revision for item in artifacts}, {revision})
            self.assertTrue(all(item.benchmark_pack == pack.provenance() for item in artifacts))

            artifact_path = next(
                path for path in evidence.glob("*.json") if path.name != "evidence-index.json"
            )
            artifact_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(PackValidationError, "hashes drifted"):
                verify_evidence(pack, evidence)

    def test_verifier_rejects_incomplete_duplicate_and_mixed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _repo, _revision, _task, manifest = self.fixture(root)
            pack = load_benchmark_pack(manifest)
            evidence = root / "evidence"
            run_pack(
                pack,
                workspace=root / "workspace",
                output_dir=evidence,
                experiment_id="replication-fixture",
                runner=self.runner(),
                model=None,
                codex_command=None,
                context_timeout_seconds=5,
                exact_command=(),
            )
            artifacts = sorted(
                path for path in evidence.glob("*.json") if path.name != "evidence-index.json"
            )

            removed = artifacts[0].read_bytes()
            artifacts[0].unlink()
            seal_evidence(pack, evidence)
            with self.assertRaisesRegex(PackValidationError, "incomplete"):
                verify_evidence(pack, evidence)
            artifacts[0].write_bytes(removed)

            duplicate = evidence / "duplicate.json"
            duplicate.write_bytes(artifacts[0].read_bytes())
            seal_evidence(pack, evidence)
            with self.assertRaisesRegex(PackValidationError, "duplicate"):
                verify_evidence(pack, evidence)
            duplicate.unlink()

            original = artifacts[0].read_text(encoding="utf-8")
            mutations = (
                ("artifact_schema_version", 2, "schema"),
                ("resolved_revision", "0" * 40, "revision"),
                ("repetition", 2, "repetition"),
            )
            for field, value, message in mutations:
                payload = json.loads(original)
                payload[field] = value
                artifacts[0].write_text(json.dumps(payload), encoding="utf-8")
                seal_evidence(pack, evidence)
                with self.subTest(field=field):
                    with self.assertRaisesRegex(PackValidationError, message):
                        verify_evidence(pack, evidence)

            payload = json.loads(original)
            payload["benchmark_pack"]["evidence_kind"] = "original"
            artifacts[0].write_text(json.dumps(payload), encoding="utf-8")
            seal_evidence(pack, evidence)
            with self.assertRaisesRegex(PackValidationError, "provenance"):
                verify_evidence(pack, evidence)

    def test_cli_validates_exports_runs_and_verifies_pack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _repo, _revision, _task, manifest = self.fixture(root)
            archive = root / "pack.tar.gz"
            evidence = root / "evidence"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                validate_exit = main(
                    ("benchmark", "pack", "validate", str(manifest), "--json")
                )
                export_exit = main(
                    (
                        "benchmark",
                        "pack",
                        "export",
                        str(manifest),
                        str(archive),
                        "--json",
                    )
                )
                run_exit = main(
                    (
                        "benchmark",
                        "pack",
                        "run",
                        str(manifest),
                        "--workspace",
                        str(root / "workspace"),
                        "--output-dir",
                        str(evidence),
                        "--experiment-id",
                        "cli-replication",
                        "--json",
                    ),
                    benchmark_runner_factory=self.runner,
                )
                verify_exit = main(
                    (
                        "benchmark",
                        "pack",
                        "verify-evidence",
                        str(manifest),
                        str(evidence),
                        "--json",
                    )
                )
            archive_exists = archive.is_file()

        self.assertEqual(validate_exit, 0)
        self.assertEqual(export_exit, 0)
        self.assertEqual(run_exit, 0)
        self.assertEqual(verify_exit, 0)
        self.assertTrue(archive_exists)


if __name__ == "__main__":
    unittest.main()
