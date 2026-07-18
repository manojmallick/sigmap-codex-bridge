import sys
import unittest
from pathlib import Path

from sigmap_codex_bridge.process import run_process


ROOT = Path(__file__).resolve().parents[1]
FAKE_CODEX = ROOT / "tests" / "fixtures" / "fake_codex.py"


class ProcessTests(unittest.TestCase):
    def test_captures_success_without_shell_interpolation(self) -> None:
        result = run_process(
            (sys.executable, str(FAKE_CODEX)),
            cwd=ROOT,
            input_text="ranked context",
            env={"FAKE_CODEX_MODE": "success"},
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.command, (sys.executable, str(FAKE_CODEX)))
        self.assertIn("turn.completed", result.stdout)

    def test_distinguishes_missing_executable(self) -> None:
        result = run_process(("definitely-not-a-real-sigmap-bridge-binary",), cwd=ROOT)

        self.assertEqual(result.launch_error, "executable_not_found")
        self.assertIsNone(result.returncode)

    def test_distinguishes_timeout(self) -> None:
        result = run_process(
            (sys.executable, str(FAKE_CODEX)),
            cwd=ROOT,
            timeout_seconds=0.05,
            env={"FAKE_CODEX_MODE": "timeout"},
        )

        self.assertTrue(result.timed_out)
        self.assertEqual(result.launch_error, "timeout")

    def test_captures_nonzero_exit(self) -> None:
        result = run_process(
            (sys.executable, str(FAKE_CODEX)),
            cwd=ROOT,
            env={"FAKE_CODEX_MODE": "failed"},
        )

        self.assertEqual(result.returncode, 7)
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
