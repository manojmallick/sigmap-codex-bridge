import json
import contextlib
import io
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from git_helpers import initialize_repo
from sigmap_codex_bridge.benchmark import BenchmarkTask
from sigmap_codex_bridge.codex import CodexRunner
from sigmap_codex_bridge.cli import main
from sigmap_codex_bridge.execution import (
    ExecutionBudget,
    ExecutionError,
    ExecutionTask,
    ResumableBenchmarkExecutor,
    diagnose_execution_state,
    load_execution_state,
    recover_execution_state,
)
from sigmap_codex_bridge.experiment import PairedBenchmarkRunner
from sigmap_codex_bridge.reporting import generate_report, load_artifacts
from sigmap_codex_bridge.sigmap import SigMapContextProvider


ROOT = Path(__file__).resolve().parents[1]
FAKE_CODEX = ROOT / "tests" / "fixtures" / "fake_codex.py"
FAKE_SIGMAP = ROOT / "tests" / "fixtures" / "fake_sigmap.py"


class SimulatedCrash(RuntimeError):
    pass


class ArtifactCrashRunner(PairedBenchmarkRunner):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.crashed = False

    def run_attempt(self, *args, **kwargs):
        artifact = super().run_attempt(*args, **kwargs)
        if not self.crashed:
            self.crashed = True
            raise SimulatedCrash("artifact persisted before state checkpoint")
        return artifact


class TrackingRunner(PairedBenchmarkRunner):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.lock = threading.Lock()
        self.active_pairs: set[str] = set()
        self.max_active_pairs = 0
        self.run_ids: list[str] = []

    def run_attempt(self, prepared, **kwargs):
        pair = f"{prepared.task_id}-r{kwargs['repetition']:03d}"
        with self.lock:
            if pair in self.active_pairs:
                raise AssertionError("conditions from one pair ran concurrently")
            self.active_pairs.add(pair)
            self.run_ids.append(kwargs["run_id"])
            self.max_active_pairs = max(self.max_active_pairs, len(self.active_pairs))
        time.sleep(0.05)
        try:
            return super().run_attempt(prepared, **kwargs)
        finally:
            with self.lock:
                self.active_pairs.remove(pair)


class ResumableExecutionTests(unittest.TestCase):
    def runner(self, runner_type=PairedBenchmarkRunner):
        return runner_type(
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

    def fixture(self, root: Path, *, repetitions: int = 2):
        repo = root / "repo"
        revision = initialize_repo(repo)
        task_file = root / "task.json"
        task = BenchmarkTask(
            schema_version=1,
            repository=str(repo),
            revision=revision,
            prompt="Create the requested fixture",
            expected_behavior="Regression tests pass",
            test_command=(sys.executable, "-c", "raise SystemExit(0)"),
            allowed_files=("codex-created.txt",),
            expected_files=("codex-created.txt",),
            repetitions=repetitions,
            timeout_seconds=5,
        )
        task_value = task.to_dict()
        if task_value["setup_command"] is None:
            del task_value["setup_command"]
        task_file.write_text(json.dumps(task_value), encoding="utf-8")
        return ExecutionTask(task_file, task)

    def execute(
        self,
        root: Path,
        task: ExecutionTask,
        *,
        runner=None,
        hook=None,
        resume: bool = False,
        budget: ExecutionBudget | None = None,
        max_workers: int = 1,
        output_name: str = "artifacts",
        state_name: str = "state.json",
        model: str = "fixture-model",
    ):
        executor = ResumableBenchmarkExecutor(
            runner or self.runner(), transition_hook=hook
        )
        return executor.execute(
            (task,),
            state_file=root / state_name,
            output_dir=root / output_name,
            experiment_id="resumable-fixture",
            sandbox="workspace-write",
            model=model,
            codex_command=None,
            start_condition="raw",
            context_timeout_seconds=5,
            worktree_root=root / f"{output_name}-worktrees",
            exact_command=("sigmap-bridge", "benchmark", "run"),
            max_workers=max_workers,
            budget=budget or ExecutionBudget(),
            resume=resume,
        )

    def test_crash_after_each_persisted_transition_resumes_without_duplicates(self) -> None:
        transitions = (
            "state_created",
            "execution_started",
            "pair_started",
            "attempt_started",
            "attempt_completed",
            "pair_completed",
            "execution_completed",
        )
        for transition in transitions:
            with self.subTest(transition=transition):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    task = self.fixture(root, repetitions=1)
                    crashed = False

                    def hook(name, _state):
                        nonlocal crashed
                        if name == transition and not crashed:
                            crashed = True
                            raise SimulatedCrash(name)

                    with self.assertRaises(SimulatedCrash):
                        self.execute(root, task, hook=hook)
                    state = self.execute(root, task, resume=True)
                    artifacts = sorted((root / "artifacts").glob("*.json"))

                    self.assertEqual(state["status"], "completed")
                    self.assertEqual(len(artifacts), 2)
                    self.assertEqual(
                        {json.loads(path.read_text())["condition"] for path in artifacts},
                        {"raw", "sigmap"},
                    )

    def test_artifact_written_before_checkpoint_is_reconciled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = self.fixture(root, repetitions=1)
            with self.assertRaises(SimulatedCrash):
                self.execute(root, task, runner=self.runner(ArtifactCrashRunner))

            interrupted = load_execution_state(root / "state.json")
            self.assertEqual(interrupted["pairs"][0]["attempts"][0]["status"], "running")
            self.assertEqual(len(list((root / "artifacts").glob("*.json"))), 1)

            completed = self.execute(root, task, resume=True)
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(len(list((root / "artifacts").glob("*.json"))), 2)

    def test_completed_artifact_missing_hash_drift_and_configuration_drift_fail_closed(self) -> None:
        for mutation, message in (("missing", "missing"), ("drift", "hash drift")):
            with self.subTest(mutation=mutation):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    task = self.fixture(root, repetitions=2)
                    state = self.execute(
                        root,
                        task,
                        budget=ExecutionBudget(max_pairs=1),
                    )
                    artifact_path = root / "artifacts" / state["pairs"][0]["attempts"][0][
                        "artifact_path"
                    ]
                    if mutation == "missing":
                        artifact_path.unlink()
                    else:
                        artifact_path.write_text("{}\n", encoding="utf-8")
                    with self.assertRaisesRegex(ExecutionError, message):
                        self.execute(
                            root,
                            task,
                            resume=True,
                            budget=ExecutionBudget(max_pairs=2),
                        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = self.fixture(root, repetitions=2)
            self.execute(root, task, budget=ExecutionBudget(max_pairs=1))
            with self.assertRaisesRegex(ExecutionError, "configuration"):
                self.execute(
                    root,
                    task,
                    resume=True,
                    budget=ExecutionBudget(max_pairs=2),
                    model="different-model",
                )

    def test_state_rejects_unknown_unsafe_and_duplicate_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = self.fixture(root, repetitions=1)
            self.execute(root, task)
            original = json.loads((root / "state.json").read_text())
            cases = []
            unknown = json.loads(json.dumps(original))
            unknown["unexpected"] = True
            cases.append((unknown, "unknown fields"))
            unsafe = json.loads(json.dumps(original))
            unsafe["pairs"][0]["attempts"][0]["artifact_path"] = "../escape.json"
            cases.append((unsafe, "safe output filename"))
            duplicate = json.loads(json.dumps(original))
            duplicate["pairs"][0]["attempts"][1]["attempt_id"] = duplicate["pairs"][0][
                "attempts"
            ][0]["attempt_id"]
            cases.append((duplicate, "unique"))
            bad_index = json.loads(json.dumps(original))
            bad_index["pairs"][0]["task_index"] = 99
            cases.append((bad_index, "task_index"))
            bad_order = json.loads(json.dumps(original))
            bad_order["pairs"][0]["order"] = ["raw", "raw"]
            cases.append((bad_order, "order"))
            missing_digest = json.loads(json.dumps(original))
            missing_digest["pairs"][0]["attempts"][0]["artifact_sha256"] = None
            cases.append((missing_digest, "artifact digest"))
            invalid_usage = json.loads(json.dumps(original))
            invalid_usage["usage"]["total_tokens"] = -1
            cases.append((invalid_usage, "non-negative"))
            for index, (value, message) in enumerate(cases):
                path = root / f"invalid-{index}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.subTest(message=message):
                    with self.assertRaisesRegex(ExecutionError, message):
                        load_execution_state(path)

    def test_pair_budgets_stop_at_boundaries_and_resume_with_higher_limits(self) -> None:
        budgets = (
            ExecutionBudget(max_pairs=1),
            ExecutionBudget(max_runtime_seconds=0.000001),
            ExecutionBudget(max_total_tokens=1),
        )
        for budget in budgets:
            with self.subTest(budget=budget):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    task = self.fixture(root, repetitions=3)
                    stopped = self.execute(root, task, budget=budget, max_workers=2)

                    self.assertEqual(stopped["status"], "stopped")
                    expected_pairs = 1 if budget.max_pairs is not None else 2
                    self.assertEqual(
                        stopped["usage"]["completed_pairs"], expected_pairs
                    )
                    self.assertEqual(
                        stopped["usage"]["completed_attempts"], expected_pairs * 2
                    )
                    self.assertEqual(
                        len(list((root / "artifacts").glob("*.json"))),
                        expected_pairs * 2,
                    )
                    self.assertIsNone(stopped["stop_reason"]["monetary_cost"])
                    if budget.max_pairs is None:
                        self.assertGreater(stopped["stop_reason"]["overshoot"], 0)

                    completed = self.execute(
                        root,
                        task,
                        resume=True,
                        budget=ExecutionBudget(max_pairs=3),
                        max_workers=2,
                    )
                    self.assertEqual(completed["status"], "completed")
                    self.assertEqual(completed["usage"]["completed_pairs"], 3)
                    self.assertEqual(len(list((root / "artifacts").glob("*.json"))), 6)

    def test_concurrent_and_serial_runs_produce_equivalent_ordered_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = self.fixture(root, repetitions=4)
            self.execute(
                root,
                task,
                output_name="serial",
                state_name="serial-state.json",
                max_workers=1,
            )
            tracking = self.runner(TrackingRunner)
            self.execute(
                root,
                task,
                runner=tracking,
                output_name="concurrent",
                state_name="concurrent-state.json",
                max_workers=2,
            )
            for output in (root / "serial", root / "concurrent"):
                for path in output.glob("*.json"):
                    value = json.loads(path.read_text())
                    value["score"]["runtime_seconds"] = 1.0
                    path.write_text(json.dumps(value), encoding="utf-8")
            serial_report = generate_report(load_artifacts(root / "serial"))
            concurrent_report = generate_report(load_artifacts(root / "concurrent"))

            self.assertGreaterEqual(tracking.max_active_pairs, 2)
            self.assertEqual(len(tracking.run_ids), len(set(tracking.run_ids)))
            self.assertEqual(serial_report, concurrent_report)
            self.assertEqual(
                list((root / "concurrent-worktrees" / "leases").glob("*.json")), []
            )

    def test_diagnose_and_recover_only_running_state_leases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = self.fixture(root, repetitions=1)
            crashed = False

            def hook(name, _state):
                nonlocal crashed
                if name == "attempt_started" and not crashed:
                    crashed = True
                    raise SimulatedCrash(name)

            with self.assertRaises(SimulatedCrash):
                self.execute(root, task, hook=hook)
            diagnostic = diagnose_execution_state(root / "state.json")
            recovered = recover_execution_state(root / "state.json")

            self.assertEqual(diagnostic["running_attempt_count"], 1)
            self.assertEqual(diagnostic["lease_diagnostics"][0]["status"], "missing")
            self.assertEqual(recovered["recovered_count"], 0)
            self.assertEqual(load_execution_state(root / "state.json")["status"], "stopped")

    def test_cli_stops_resumes_and_diagnoses_persisted_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = self.fixture(root, repetitions=2)
            state_path = root / "state.json"
            output_dir = root / "artifacts"
            worktrees = root / "worktrees"

            def arguments(*extra: str) -> tuple[str, ...]:
                return (
                    "benchmark",
                    "run",
                    str(task.task_file),
                    "--experiment-id",
                    "cli-resume",
                    "--output-dir",
                    str(output_dir),
                    "--worktree-root",
                    str(worktrees),
                    "--state-file",
                    str(state_path),
                    "--context-timeout",
                    "5",
                    "--json",
                    *extra,
                )

            stopped_output = io.StringIO()
            with contextlib.redirect_stdout(stopped_output):
                stopped_exit = main(
                    arguments("--max-pairs", "1"),
                    benchmark_runner_factory=self.runner,
                )
            diagnose_output = io.StringIO()
            with contextlib.redirect_stdout(diagnose_output):
                diagnose_exit = main(
                    ("benchmark", "execution", "diagnose", str(state_path), "--json")
                )
            completed_output = io.StringIO()
            with contextlib.redirect_stdout(completed_output):
                completed_exit = main(
                    arguments("--resume", "--max-pairs", "2"),
                    benchmark_runner_factory=self.runner,
                )

            payloads = [
                json.loads(output.getvalue())
                for output in (stopped_output, diagnose_output, completed_output)
            ]
            self.assertEqual((stopped_exit, diagnose_exit, completed_exit), (0, 0, 0))
            self.assertEqual(payloads[0]["status"], "stopped")
            self.assertEqual(payloads[1]["running_attempt_count"], 0)
            self.assertEqual(payloads[2]["status"], "completed")
            self.assertEqual(payloads[2]["artifact_count"], 4)


if __name__ == "__main__":
    unittest.main()
