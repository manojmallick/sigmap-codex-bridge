import json
import sys
import tempfile
import unittest
from pathlib import Path

from git_helpers import initialize_repo
from sigmap_codex_bridge.benchmark import BenchmarkTask
from sigmap_codex_bridge.codex import CodexRunner
from sigmap_codex_bridge.experiment import PairedBenchmarkRunner, condition_order
from sigmap_codex_bridge.sigmap import SigMapContextProvider


ROOT = Path(__file__).resolve().parents[1]
FAKE_CODEX = ROOT / "tests" / "fixtures" / "fake_codex.py"
FAKE_SIGMAP = ROOT / "tests" / "fixtures" / "fake_sigmap.py"


class PairedBenchmarkRunnerTests(unittest.TestCase):
    def runner(self, *, codex_mode: str = "write") -> PairedBenchmarkRunner:
        return PairedBenchmarkRunner(
            context_provider=SigMapContextProvider(
                command=(sys.executable, str(FAKE_SIGMAP)),
                env={"FAKE_SIGMAP_MODE": "ready"},
            ),
            codex_runner_factory=lambda timeout: CodexRunner(
                command=(sys.executable, str(FAKE_CODEX)),
                timeout_seconds=timeout,
                env={"FAKE_CODEX_MODE": codex_mode},
            ),
        )

    def task(self, repo: Path, revision: str, *, repetitions: int = 2) -> BenchmarkTask:
        return BenchmarkTask(
            schema_version=1,
            repository=str(repo),
            revision=revision,
            prompt="Create the requested fixture",
            expected_behavior="Regression tests pass",
            test_command=(sys.executable, "-c", "raise SystemExit(0)"),
            static_check_commands=((sys.executable, "--version"),),
            allowed_files=("codex-created.txt",),
            expected_files=("codex-created.txt",),
            repetitions=repetitions,
            timeout_seconds=5,
        )

    def test_condition_order_alternates_deterministically(self) -> None:
        self.assertEqual(condition_order(1), ("raw", "sigmap"))
        self.assertEqual(condition_order(2), ("sigmap", "raw"))
        self.assertEqual(condition_order(1, "sigmap"), ("sigmap", "raw"))
        with self.assertRaises(ValueError):
            condition_order(0)

    def test_runs_complete_pairs_from_one_revision_and_retains_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            repo = temp / "repo"
            revision = initialize_repo(repo)
            output = temp / "artifacts"
            task_file = temp / "task.yaml"
            task_file.write_text("fixture\n", encoding="utf-8")

            artifacts = self.runner().run_task(
                self.task(repo, revision),
                task_file=task_file,
                output_dir=output,
                experiment_id="fixture-experiment",
                model="fixture-model",
                worktree_root=temp / "worktrees",
                exact_command=("sigmap-bridge", "benchmark", "run"),
            )

            self.assertEqual(len(artifacts), 4)
            self.assertEqual(
                [(item.repetition, item.condition) for item in artifacts],
                [(1, "raw"), (1, "sigmap"), (2, "sigmap"), (2, "raw")],
            )
            self.assertEqual({item.resolved_revision for item in artifacts}, {revision})
            self.assertTrue(all(item.worktree_cleaned for item in artifacts))
            self.assertTrue(all(item.score.passed for item in artifacts))
            self.assertTrue(all(item.score.target_file_recall == 1.0 for item in artifacts))
            self.assertEqual(len(list(output.glob("*.json"))), 4)
            self.assertEqual(list((temp / "worktrees" / "leases").glob("*.json")), [])

            raw = next(item for item in artifacts if item.condition == "raw")
            grounded = next(item for item in artifacts if item.condition == "sigmap")
            self.assertEqual(raw.context.status.value, "disabled")
            self.assertEqual(grounded.context.status.value, "ready")
            self.assertIn("--model", raw.codex.process.command)
            payload = json.loads(next(output.glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(payload["artifact_schema_version"], 1)
            self.assertIn("bridge", payload)
            self.assertNotIn("context", payload["score"])

    def test_codex_failures_are_scored_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            repo = temp / "repo"
            revision = initialize_repo(repo)
            task_file = temp / "task.yaml"
            task_file.write_text("fixture\n", encoding="utf-8")

            artifacts = self.runner(codex_mode="failed").run_task(
                self.task(repo, revision, repetitions=1),
                task_file=task_file,
                output_dir=temp / "artifacts",
                experiment_id="failure-experiment",
                worktree_root=temp / "worktrees",
            )

            self.assertEqual(len(artifacts), 2)
            self.assertTrue(all(not item.score.passed for item in artifacts))
            self.assertTrue(
                all("Codex failed: failed" in item.failure_details for item in artifacts)
            )
            self.assertEqual(len(list((temp / "artifacts").glob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
