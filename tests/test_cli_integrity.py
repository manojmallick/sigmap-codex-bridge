import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from git_helpers import initialize_repo
from sigmap_codex_bridge.audit import AuditLog
from sigmap_codex_bridge.cli import main
from sigmap_codex_bridge.worktree import WorktreeManager


class IntegrityCliTests(unittest.TestCase):
    def test_verify_reports_valid_and_tampered_chains(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit_path = Path(directory) / "audit.jsonl"
            log = AuditLog(audit_path)
            log.record(
                run_id="run-one",
                base_commit="a" * 40,
                condition="raw",
                context="",
                codex_thread_id="thread-one",
                exit_code=0,
                usage={},
                source_dirty=False,
                changes=[],
                timestamp="2026-07-18T00:00:00+00:00",
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                valid_code = main(["verify", "--audit-log", str(audit_path), "--json"])
            self.assertEqual(valid_code, 0)
            self.assertTrue(json.loads(output.getvalue())["valid"])

            audit_path.write_text("{}\n", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                invalid_code = main(
                    ["verify", "--audit-log", str(audit_path), "--json"]
                )
            self.assertEqual(invalid_code, 44)
            self.assertFalse(json.loads(output.getvalue())["valid"])

    def test_cleanup_recovers_exact_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            repo = temp / "repo"
            base_commit = initialize_repo(repo)
            root = temp / "worktrees"
            lease = WorktreeManager(repo, root=root).create("run-one", base_commit)

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(
                    [
                        "cleanup",
                        "run-one",
                        "--repo",
                        str(repo),
                        "--worktree-root",
                        str(root),
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(json.loads(output.getvalue())["cleaned"])
            self.assertFalse(Path(lease.path).exists())


if __name__ == "__main__":
    unittest.main()
