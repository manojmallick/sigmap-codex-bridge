import tempfile
import unittest
from pathlib import Path

from git_helpers import git, initialize_repo
from sigmap_codex_bridge.git import GitRepository


class GitRepositoryTests(unittest.TestCase):
    def test_captures_added_modified_renamed_and_deleted_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            base_commit = initialize_repo(repo)

            (repo / "modified.txt").write_text("after\n", encoding="utf-8")
            (repo / "deleted.txt").unlink()
            git(repo, "mv", "renamed.txt", "new-name.txt")
            (repo / "added file.txt").write_text("new\n", encoding="utf-8")

            state = GitRepository(repo).inspect()
            by_path = {change.path: change for change in state.changes}

            self.assertEqual(state.base_commit, base_commit)
            self.assertTrue(state.dirty)
            self.assertEqual(by_path["modified.txt"].status, "modified")
            self.assertEqual(by_path["deleted.txt"].status, "deleted")
            self.assertEqual(by_path["added file.txt"].status, "added")
            self.assertEqual(by_path["new-name.txt"].status, "renamed")
            self.assertEqual(by_path["new-name.txt"].original_path, "renamed.txt")

    def test_clean_repository_has_no_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            initialize_repo(repo)

            state = GitRepository(repo).inspect()

            self.assertFalse(state.dirty)
            self.assertEqual(state.changes, ())


if __name__ == "__main__":
    unittest.main()
