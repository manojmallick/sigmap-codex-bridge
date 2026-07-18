import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from sigmap_codex_bridge.cli import main
from sigmap_codex_bridge.submission import validate_submission


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "submission" / "build-week-2026.json"
REPORT = ROOT / "benchmarks" / "results" / "build-week-2026-07-18" / "report.json"


def check(result, name: str):
    return next(item for item in result.checks if item.name == name)


class SubmissionCandidateTests(unittest.TestCase):
    def fixture(self, root: Path, *, ready: bool = False) -> Path:
        submission_dir = root / "submission"
        submission_dir.mkdir()
        report_path = root / "report.json"
        report_path.write_bytes(REPORT.read_bytes())
        payload = json.loads(METADATA.read_text(encoding="utf-8"))
        payload["evidence"]["report_path"] = "report.json"
        if ready:
            payload["release"]["status"] = "ready"
            payload["external"] = {
                "feedback_session_id": "session-verified-by-feedback",
                "video_url": "https://youtu.be/example",
                "devpost_url": "https://devpost.com/software/sigmap-codex-bridge",
            }
        path = submission_dir / "candidate.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_checked_in_candidate_is_valid_but_externally_blocked(self) -> None:
        result = validate_submission(METADATA)

        self.assertTrue(result.valid)
        self.assertFalse(result.submission_ready)
        self.assertEqual(check(result, "report_sha256").status, "ok")
        self.assertEqual(check(result, "measured_results").status, "ok")
        self.assertEqual(check(result, "experiment_id").status, "ok")
        self.assertEqual(check(result, "feedback_session_id").status, "warn")
        self.assertEqual(check(result, "release_status").status, "ok")

    def test_complete_real_values_make_candidate_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = validate_submission(self.fixture(Path(directory), ready=True))

        self.assertTrue(result.valid)
        self.assertTrue(result.submission_ready)

    def test_future_or_malformed_candidate_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.fixture(root)
            payload = json.loads(path.read_text(encoding="utf-8"))
            for version in ("0.9.0", "next"):
                payload["release"]["version"] = version
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(version=version):
                    result = validate_submission(path)
                    self.assertFalse(result.valid)
                    self.assertEqual(check(result, "package_version").status, "fail")

    def test_tampered_numbers_and_escaped_report_path_fail_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.fixture(root)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["evidence"]["measured_results"]["raw_passed"] = 10
            path.write_text(json.dumps(payload), encoding="utf-8")
            mismatched = validate_submission(path)
            payload["evidence"]["report_path"] = "../outside.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            escaped = validate_submission(path)

        self.assertFalse(mismatched.valid)
        self.assertEqual(check(mismatched, "measured_results").status, "fail")
        self.assertFalse(escaped.valid)
        self.assertEqual(check(escaped, "report_path").status, "fail")

    def test_cli_distinguishes_integrity_from_submission_readiness(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            advisory_exit = main(("submission", "validate", str(METADATA), "--json"))
            required_exit = main(
                (
                    "submission",
                    "validate",
                    str(METADATA),
                    "--require-ready",
                    "--json",
                )
            )

        self.assertEqual(advisory_exit, 0)
        self.assertEqual(required_exit, 2)

    def test_judge_documents_match_the_frozen_headline_result(self) -> None:
        documents = (
            ROOT / "README.md",
            ROOT / "docs" / "submission" / "measured-results-and-codex.md",
            ROOT / "docs" / "submission" / "demo-script.md",
            ROOT / "docs" / "submission" / "devpost-submission.md",
        )
        required = (
            "9/9",
            "249.089",
            "186.590",
            "766,538",
            "562,358",
            "zero-credit",
            "sigmap-bridge demo",
        )
        for path in documents:
            content = path.read_text(encoding="utf-8")
            for value in required:
                with self.subTest(path=path.name, value=value):
                    self.assertIn(value, content)

    def test_submission_diagrams_and_timed_demo_sections_are_present(self) -> None:
        architecture = (
            ROOT / "docs" / "submission" / "architecture.md"
        ).read_text(encoding="utf-8")
        demo = (ROOT / "docs" / "submission" / "demo-script.md").read_text(
            encoding="utf-8"
        )

        self.assertGreaterEqual(architecture.count("```mermaid"), 3)
        self.assertIn("Independent scorer", architecture)
        self.assertIn("Bridge Audit Log", architecture)
        self.assertIn("2:40 target", demo)
        self.assertIn("## 2:30–2:40 — Close", demo)


if __name__ == "__main__":
    unittest.main()
