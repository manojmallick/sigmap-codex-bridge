import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

from sigmap_codex_bridge.bridge import Bridge, ExitCode
from sigmap_codex_bridge.cli import main
from sigmap_codex_bridge.codex import CodexRunner
from sigmap_codex_bridge.sigmap import SigMapContextProvider


ROOT = Path(__file__).resolve().parents[1]
FAKE_CODEX = ROOT / "tests" / "fixtures" / "fake_codex.py"
FAKE_SIGMAP = ROOT / "tests" / "fixtures" / "fake_sigmap.py"


def bridge_factory(sigmap_mode: str = "ready", codex_mode: str = "success"):
    def factory() -> Bridge:
        sigmap_command = (
            ("definitely-not-a-real-sigmap-binary",)
            if sigmap_mode == "unavailable"
            else (sys.executable, str(FAKE_SIGMAP))
        )
        codex_command = (
            ("definitely-not-a-real-codex-binary",)
            if codex_mode == "unavailable"
            else (sys.executable, str(FAKE_CODEX))
        )
        return Bridge(
            context_provider=SigMapContextProvider(
                command=sigmap_command,
                timeout_seconds=0.05 if sigmap_mode == "timeout" else 1.0,
                env={"FAKE_SIGMAP_MODE": sigmap_mode},
            ),
            codex_runner=CodexRunner(
                command=codex_command,
                timeout_seconds=0.05 if codex_mode == "timeout" else 1.0,
                env={"FAKE_CODEX_MODE": codex_mode},
            ),
        )

    return factory


class BridgeAndCliTests(unittest.TestCase):
    def run_cli(
        self, argv: list[str], *, sigmap: str = "ready", codex: str = "success"
    ):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(argv, bridge_factory=bridge_factory(sigmap, codex))
        return exit_code, json.loads(output.getvalue())

    def test_sigmap_mode_runs_codex_with_context(self) -> None:
        exit_code, payload = self.run_cli(
            ["run", "fix auth", "--repo", str(ROOT), "--json"]
        )

        self.assertEqual(exit_code, ExitCode.SUCCESS)
        self.assertEqual(payload["requested_context"], "sigmap")
        self.assertEqual(payload["context_source"], "sigmap")
        self.assertEqual(payload["codex"]["status"], "succeeded")
        self.assertIn("context=True", payload["codex"]["final_message"])

    def test_raw_mode_is_explicit(self) -> None:
        exit_code, payload = self.run_cli(
            [
                "run",
                "fix auth",
                "--repo",
                str(ROOT),
                "--no-sigmap",
                "--json",
            ],
            sigmap="failed",
        )

        self.assertEqual(exit_code, ExitCode.SUCCESS)
        self.assertEqual(payload["requested_context"], "none")
        self.assertEqual(payload["context"]["status"], "disabled")
        self.assertIn("context=False", payload["codex"]["final_message"])

    def test_context_failures_are_fail_closed_with_stable_exit_codes(self) -> None:
        cases = (
            ("unavailable", ExitCode.SIGMAP_UNAVAILABLE, "unavailable"),
            ("missing_index", ExitCode.SIGMAP_INDEX_MISSING, "missing_index"),
            ("timeout", ExitCode.SIGMAP_TIMEOUT, "timed_out"),
            ("failed", ExitCode.SIGMAP_FAILED, "failed"),
        )
        for mode, expected_code, expected_status in cases:
            with self.subTest(mode=mode):
                exit_code, payload = self.run_cli(
                    ["run", "fix auth", "--repo", str(ROOT), "--json"],
                    sigmap=mode,
                )

                self.assertEqual(exit_code, expected_code)
                self.assertEqual(payload["context"]["status"], expected_status)
                self.assertEqual(payload["context_source"], "none")
                self.assertIsNone(payload["codex"])

    def test_codex_failures_have_stable_exit_codes(self) -> None:
        cases = (
            ("unavailable", ExitCode.CODEX_UNAVAILABLE, "unavailable"),
            ("timeout", ExitCode.CODEX_TIMEOUT, "timed_out"),
            ("malformed", ExitCode.CODEX_MALFORMED_JSONL, "malformed_jsonl"),
            ("failed", ExitCode.CODEX_FAILED, "failed"),
        )
        for mode, expected_code, expected_status in cases:
            with self.subTest(mode=mode):
                exit_code, payload = self.run_cli(
                    [
                        "run",
                        "fix",
                        "--repo",
                        str(ROOT),
                        "--no-sigmap",
                        "--json",
                    ],
                    codex=mode,
                )

                self.assertEqual(exit_code, expected_code)
                self.assertEqual(payload["codex"]["status"], expected_status)


if __name__ == "__main__":
    unittest.main()
