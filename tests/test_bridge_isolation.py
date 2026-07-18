import json
import sys
import tempfile
import unittest
from pathlib import Path

from git_helpers import initialize_repo
from sigmap_codex_bridge.audit import AuditLog
from sigmap_codex_bridge.bridge import Bridge, ExitCode
from sigmap_codex_bridge.codex import CodexRunner
from sigmap_codex_bridge.sigmap import SigMapContextProvider


ROOT = Path(__file__).resolve().parents[1]
FAKE_CODEX = ROOT / "tests" / "fixtures" / "fake_codex.py"
FAKE_SIGMAP = ROOT / "tests" / "fixtures" / "fake_sigmap.py"


class BridgeIsolationTests(unittest.TestCase):
    def test_run_is_isolated_diffed_audited_and_cleaned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            repo = temp / "repo"
            base_commit = initialize_repo(repo)
            (repo / "source-only.txt").write_text("must not leak", encoding="utf-8")
            audit_path = temp / "audit.jsonl"
            bridge = Bridge(
                context_provider=SigMapContextProvider(
                    command=(sys.executable, str(FAKE_SIGMAP)),
                    env={"FAKE_SIGMAP_MODE": "ready"},
                ),
                codex_runner=CodexRunner(
                    command=(sys.executable, str(FAKE_CODEX)),
                    env={"FAKE_CODEX_MODE": "write"},
                ),
            )

            result = bridge.run(
                "write fixture",
                repo,
                worktree_root=temp / "worktrees",
                audit_path=audit_path,
            )

            self.assertEqual(result.exit_code, ExitCode.SUCCESS)
            self.assertEqual(result.base_commit, base_commit)
            self.assertTrue(result.source_dirty)
            self.assertTrue(result.worktree_cleaned)
            self.assertFalse(Path(result.execution_path).exists())
            self.assertFalse((repo / "codex-created.txt").exists())
            self.assertIn("leaked=False", result.codex.final_message)
            self.assertEqual(
                [(change.status, change.path) for change in result.changes],
                [("added", "codex-created.txt")],
            )
            self.assertEqual(len(result.audit_entry_hash), 64)
            self.assertTrue(AuditLog(audit_path).verify().valid)

            entry = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual(entry["base_commit"], base_commit)
            self.assertEqual(entry["condition"], "sigmap")
            self.assertNotIn("context", entry)
            self.assertNotIn("task", entry)

    def test_unexpected_runner_error_still_cleans_worktree(self) -> None:
        class ExplodingRunner:
            def run(self, *args, **kwargs):
                raise RuntimeError("synthetic unexpected error")

        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            repo = temp / "repo"
            initialize_repo(repo)
            bridge = Bridge(
                context_provider=SigMapContextProvider(
                    command=(sys.executable, str(FAKE_SIGMAP)),
                    env={"FAKE_SIGMAP_MODE": "ready"},
                ),
                codex_runner=ExplodingRunner(),
            )

            with self.assertRaisesRegex(RuntimeError, "synthetic unexpected error"):
                bridge.run(
                    "explode",
                    repo,
                    worktree_root=temp / "worktrees",
                    audit_path=temp / "audit.jsonl",
                )

            runs_dir = temp / "worktrees" / "runs"
            self.assertEqual(list(runs_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
