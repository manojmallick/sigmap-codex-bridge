import sys
import tempfile
import unittest
from pathlib import Path

from sigmap_codex_bridge.benchmark import BenchmarkTask
from sigmap_codex_bridge.preflight import preflight_task

from git_helpers import initialize_repo


class PreflightTests(unittest.TestCase):
    def task(
        self,
        repo: Path,
        revision: str,
        *,
        setup: tuple[str, ...] | None = None,
        test: tuple[str, ...] | None = None,
    ) -> BenchmarkTask:
        return BenchmarkTask(
            schema_version=1,
            repository=str(repo),
            revision=revision,
            prompt="Change behavior",
            expected_behavior="Tests continue to pass",
            setup_command=setup,
            test_command=test or (sys.executable, "-c", "raise SystemExit(0)"),
            static_check_commands=((sys.executable, "--version"),),
        )

    def test_accepts_passing_clean_baseline_and_cleans_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            revision = initialize_repo(repo)
            worktrees = root / "worktrees"

            result = preflight_task(
                self.task(repo, revision), worktree_root=worktrees
            )

            self.assertTrue(result.valid, result.to_dict())
            self.assertEqual(result.revision, revision)
            self.assertTrue(any(check.name == "baseline_tests" for check in result.checks))
            self.assertTrue(any(check.name == "cleanup" for check in result.checks))
            self.assertEqual(list((worktrees / "leases").glob("*.json")), [])

    def test_rejects_missing_revision_and_dirty_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            revision = initialize_repo(repo)

            missing = preflight_task(
                self.task(repo, "missing-revision"),
                worktree_root=root / "missing-worktrees",
            )
            (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            dirty = preflight_task(
                self.task(repo, revision), worktree_root=root / "dirty-worktrees"
            )

        self.assertFalse(missing.valid)
        self.assertEqual(missing.checks[-1].name, "revision")
        self.assertFalse(dirty.valid)
        self.assertEqual(dirty.checks[-1].name, "source_clean")

    def test_rejects_unavailable_setup_or_test_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            revision = initialize_repo(repo)

            missing_setup = preflight_task(
                self.task(repo, revision, setup=("missing-setup-command-bridge",)),
                worktree_root=root / "setup-worktrees",
            )
            missing_test = preflight_task(
                self.task(repo, revision, test=("missing-test-command-bridge",)),
                worktree_root=root / "test-worktrees",
            )

        self.assertFalse(missing_setup.valid)
        self.assertIn("setup_command", [check.name for check in missing_setup.checks])
        self.assertFalse(missing_test.valid)
        self.assertIn("commands_available", [check.name for check in missing_test.checks])
        self.assertEqual(missing_setup.checks[-1].name, "cleanup")
        self.assertEqual(missing_test.checks[-1].name, "cleanup")

    def test_rejects_setup_failure_and_already_failing_tests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            revision = initialize_repo(repo)

            setup_failure = preflight_task(
                self.task(
                    repo,
                    revision,
                    setup=(sys.executable, "-c", "raise SystemExit(3)"),
                ),
                worktree_root=root / "setup-failure-worktrees",
            )
            test_failure = preflight_task(
                self.task(
                    repo,
                    revision,
                    test=(sys.executable, "-c", "raise SystemExit(4)"),
                ),
                worktree_root=root / "test-failure-worktrees",
            )

        self.assertFalse(setup_failure.valid)
        self.assertFalse(test_failure.valid)
        self.assertIn("baseline_tests", [check.name for check in test_failure.checks])

    def test_rejects_setup_that_changes_versioned_candidate_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            revision = initialize_repo(repo)
            result = preflight_task(
                self.task(
                    repo,
                    revision,
                    setup=(
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('generated.txt').write_text('x')",
                    ),
                ),
                worktree_root=root / "worktrees",
            )

        self.assertFalse(result.valid)
        setup_clean = next(
            check for check in result.checks if check.name == "setup_clean"
        )
        self.assertFalse(setup_clean.passed)


if __name__ == "__main__":
    unittest.main()
