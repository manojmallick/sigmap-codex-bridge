import sys
import unittest
from pathlib import Path

from sigmap_codex_bridge.codex import CodexRunner, CodexStatus


ROOT = Path(__file__).resolve().parents[1]
FAKE_CODEX = ROOT / "tests" / "fixtures" / "fake_codex.py"


class CodexRunnerTests(unittest.TestCase):
    def runner(self, mode: str, timeout: float = 1.0) -> CodexRunner:
        return CodexRunner(
            command=(sys.executable, str(FAKE_CODEX)),
            timeout_seconds=timeout,
            env={"FAKE_CODEX_MODE": mode},
        )

    def test_passes_context_via_stdin_and_parses_jsonl(self) -> None:
        result = self.runner("success").run(
            "fix auth",
            ROOT,
            context="ranked context",
            sandbox="workspace-write",
        )

        self.assertEqual(result.status, CodexStatus.SUCCEEDED)
        self.assertEqual(result.thread_id, "thread-fixture")
        self.assertEqual(result.file_changes, ("src/auth.py", "tests/test_auth.py"))
        self.assertEqual(result.usage.input_tokens, 120)
        self.assertEqual(result.usage.cached_input_tokens, 20)
        self.assertEqual(result.final_message, "fixture completed; context=True")
        self.assertEqual(
            result.process.command[-5:],
            ("exec", "--json", "--sandbox", "workspace-write", "fix auth"),
        )

    def test_raw_mode_sends_no_context(self) -> None:
        result = self.runner("success").run(
            "fix auth", ROOT, context=None, sandbox="read-only"
        )

        self.assertEqual(result.final_message, "fixture completed; context=False")

    def test_distinguishes_malformed_and_incomplete_jsonl(self) -> None:
        malformed = self.runner("malformed").run(
            "fix", ROOT, context=None, sandbox="read-only"
        )
        incomplete = self.runner("incomplete").run(
            "fix", ROOT, context=None, sandbox="read-only"
        )

        self.assertEqual(malformed.status, CodexStatus.MALFORMED_JSONL)
        self.assertEqual(incomplete.status, CodexStatus.MALFORMED_JSONL)

    def test_distinguishes_timeout_and_nonzero_exit(self) -> None:
        timed_out = self.runner("timeout", 0.05).run(
            "fix", ROOT, context=None, sandbox="read-only"
        )
        failed = self.runner("failed").run(
            "fix", ROOT, context=None, sandbox="read-only"
        )

        self.assertEqual(timed_out.status, CodexStatus.TIMED_OUT)
        self.assertEqual(failed.status, CodexStatus.FAILED)
        self.assertEqual(failed.detail, "synthetic failure")


if __name__ == "__main__":
    unittest.main()
