import json
import tempfile
import unittest
from pathlib import Path

from git_helpers import initialize_repo
from sigmap_codex_bridge.worktree import WorktreeError, WorktreeManager


class WorktreeManagerTests(unittest.TestCase):
    def test_same_base_worktrees_are_isolated_and_cleanup_is_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            repo = temp / "repo"
            base_commit = initialize_repo(repo)
            manager = WorktreeManager(repo, root=temp / "managed")
            first = manager.create("run-one", base_commit)
            second = manager.create("run-two", base_commit)

            (Path(first.path) / "only-first.txt").write_text("first", encoding="utf-8")
            self.assertFalse((Path(second.path) / "only-first.txt").exists())
            self.assertFalse((repo / "only-first.txt").exists())

            manager.cleanup(first)
            self.assertFalse(Path(first.path).exists())
            self.assertTrue(Path(second.path).exists())
            manager.cleanup(second)
            self.assertFalse(Path(second.path).exists())

    def test_stale_lease_can_be_recovered_by_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            repo = temp / "repo"
            base_commit = initialize_repo(repo)
            root = temp / "managed"
            manager = WorktreeManager(repo, root=root)
            lease = manager.create("interrupted-run", base_commit)

            recovered = WorktreeManager(repo, root=root).recover("interrupted-run")

            self.assertEqual(recovered, lease)
            self.assertFalse(Path(lease.path).exists())
            self.assertFalse((root / "leases" / "interrupted-run.json").exists())

    def test_tampered_lease_cannot_target_unrelated_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            repo = temp / "repo"
            base_commit = initialize_repo(repo)
            root = temp / "managed"
            unrelated = temp / "unrelated"
            unrelated.mkdir()
            manager = WorktreeManager(repo, root=root)
            manager.create("run-one", base_commit)
            lease_path = root / "leases" / "run-one.json"
            value = json.loads(lease_path.read_text(encoding="utf-8"))
            value["path"] = str(unrelated)
            lease_path.write_text(json.dumps(value), encoding="utf-8")

            with self.assertRaises(WorktreeError):
                manager.recover("run-one")

            self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()
