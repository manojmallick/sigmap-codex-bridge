import sys
import unittest
from pathlib import Path

from sigmap_codex_bridge.sigmap import ContextStatus, SigMapContextProvider


ROOT = Path(__file__).resolve().parents[1]
FAKE_SIGMAP = ROOT / "tests" / "fixtures" / "fake_sigmap.py"


class SigMapContextProviderTests(unittest.TestCase):
    def provider(self, mode: str, timeout: float = 1.0) -> SigMapContextProvider:
        return SigMapContextProvider(
            command=(sys.executable, str(FAKE_SIGMAP)),
            timeout_seconds=timeout,
            env={"FAKE_SIGMAP_MODE": mode},
        )

    def test_returns_ready_context(self) -> None:
        result = self.provider("ready").retrieve("fix auth", ROOT)

        self.assertEqual(result.status, ContextStatus.READY)
        self.assertIn("validate_token", result.context)
        self.assertGreater(result.word_count, 0)

    def test_reads_generated_query_context_instead_of_cli_summary(self) -> None:
        result = self.provider("ready_file").retrieve("task", ROOT)

        self.assertEqual(result.status, ContextStatus.READY)
        self.assertIn("src/actual.py", result.context)
        self.assertNotIn("query context written", result.context)

    def test_distinguishes_missing_index(self) -> None:
        result = self.provider("missing_index").retrieve("fix auth", ROOT)

        self.assertEqual(result.status, ContextStatus.MISSING_INDEX)

    def test_distinguishes_timeout(self) -> None:
        result = self.provider("timeout", 0.05).retrieve("fix auth", ROOT)

        self.assertEqual(result.status, ContextStatus.TIMED_OUT)

    def test_distinguishes_failed_and_empty_context(self) -> None:
        failed = self.provider("failed").retrieve("fix auth", ROOT)
        empty = self.provider("empty").retrieve("fix auth", ROOT)

        self.assertEqual(failed.status, ContextStatus.FAILED)
        self.assertEqual(empty.status, ContextStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
