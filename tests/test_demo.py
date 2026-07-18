import contextlib
import hashlib
import io
import json
import unittest
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

from sigmap_codex_bridge.cli import main
from sigmap_codex_bridge.demo import REPLAY_LABEL, render_replay, replay_demo


ROOT = Path(__file__).resolve().parents[1]
SOURCE_REPORT = ROOT / "benchmarks" / "results" / "build-week-2026-07-18" / "report.json"


class ZeroCreditDemoTests(unittest.TestCase):
    def test_packaged_report_is_exact_checked_in_evidence(self) -> None:
        packaged = files("sigmap_codex_bridge").joinpath(
            "demo_data", "report.json"
        ).read_bytes()
        source = SOURCE_REPORT.read_bytes()

        self.assertEqual(packaged, source)
        self.assertEqual(
            hashlib.sha256(packaged).hexdigest(),
            "689698a2525cb77142a3aae33295ef6d7de18a6d0bb848c85546f70c61acf490",
        )

    def test_replay_makes_no_subprocess_or_network_calls(self) -> None:
        with (
            patch("subprocess.run", side_effect=AssertionError("subprocess called")),
            patch("urllib.request.urlopen", side_effect=AssertionError("network called")),
        ):
            payload = replay_demo()

        self.assertTrue(payload["replay"])
        self.assertEqual(payload["live_calls"], 0)
        self.assertFalse(payload["credits_required"])
        self.assertEqual(payload["report"]["artifact_count"], 18)
        self.assertEqual(
            payload["source"]["report_commit"],
            "d7c9877906af083ae0724e50175f859386a52e7b",
        )
        self.assertEqual(len(payload["events"]), 5)
        self.assertIn(REPLAY_LABEL, render_replay(payload))
        self.assertIn("Live calls made: 0", render_replay(payload))

    def test_demo_cli_labels_human_and_json_replay(self) -> None:
        human = io.StringIO()
        with contextlib.redirect_stdout(human):
            human_exit = main(("demo",))
        machine = io.StringIO()
        with contextlib.redirect_stdout(machine):
            json_exit = main(("demo", "--json"))

        payload = json.loads(machine.getvalue())
        self.assertEqual(human_exit, 0)
        self.assertEqual(json_exit, 0)
        self.assertIn("ZERO-CREDIT REPLAY", human.getvalue())
        self.assertEqual(payload["mode"], "replay")
        self.assertEqual(payload["live_calls"], 0)


if __name__ == "__main__":
    unittest.main()
