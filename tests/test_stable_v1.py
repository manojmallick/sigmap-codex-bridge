import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from sigmap_codex_bridge.attestation import (
    sign_attestation,
    verify_attestation,
)
from sigmap_codex_bridge.bridge import Bridge, ExitCode
from sigmap_codex_bridge.cli import main
from sigmap_codex_bridge.codex import CodexResult, CodexStatus
from sigmap_codex_bridge.dashboard import generate_dashboard
from sigmap_codex_bridge.process import ProcessResult
from sigmap_codex_bridge.sigmap import (
    ContextProvider,
    ContextResult,
    ContextStatus,
    RawContextProvider,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "benchmarks" / "results" / "build-week-2026-07-18" / "artifacts"
DASHBOARD = ROOT / "benchmarks" / "dashboard" / "build-week-2026.json"
KEY = b"stable-v1-test-key-material-32-bytes-long"


class StubProvider:
    name = "stub"

    def __init__(self, result: ContextResult) -> None:
        self.result = result

    def retrieve(self, task: str, repo_path: str | Path) -> ContextResult:
        del task, repo_path
        return self.result


class RecordingCodexRunner:
    def __init__(self) -> None:
        self.context: str | None = "not-called"

    def run(
        self,
        task: str,
        repo_path: str | Path,
        *,
        context: str | None,
        sandbox: str,
    ) -> CodexResult:
        del task, repo_path, sandbox
        self.context = context
        return CodexResult(
            status=CodexStatus.SUCCEEDED,
            process=ProcessResult(
                command=("codex",),
                cwd=str(ROOT),
                stdout="",
                stderr="",
                returncode=0,
                duration_seconds=0.0,
            ),
        )


class StableProviderTests(unittest.TestCase):
    def test_public_provider_contract_and_raw_provider(self) -> None:
        provider = StubProvider(ContextResult(status=ContextStatus.READY, context="x"))

        self.assertIsInstance(provider, ContextProvider)
        self.assertEqual(RawContextProvider().retrieve("task", ROOT).status, ContextStatus.DISABLED)

    def test_raw_provider_executes_without_context(self) -> None:
        codex = RecordingCodexRunner()
        bridge = Bridge(
            context_provider=RawContextProvider(),
            codex_runner=codex,  # type: ignore[arg-type]
            isolate_runs=False,
            audit_runs=False,
        )

        result = bridge.run("inspect", ROOT)

        self.assertEqual(result.exit_code, ExitCode.SUCCESS)
        self.assertEqual(result.requested_context, "raw")
        self.assertIsNone(codex.context)

    def test_alternative_provider_failure_fails_closed(self) -> None:
        bridge = Bridge(
            context_provider=StubProvider(
                ContextResult(status=ContextStatus.FAILED, detail="provider failed")
            ),
            isolate_runs=False,
            audit_runs=False,
        )

        result = bridge.run("inspect", ROOT)

        self.assertEqual(result.requested_context, "stub")
        self.assertEqual(result.exit_code, ExitCode.SIGMAP_FAILED)
        self.assertIsNone(result.codex)


class ProvenanceAttestationTests(unittest.TestCase):
    def test_round_trip_and_expected_subject_constraints(self) -> None:
        payload = {"experiment_id": "stable-v1", "artifact_count": 2}
        envelope = sign_attestation(payload, key=KEY, key_id="release-key-2026")

        result = verify_attestation(
            envelope,
            key=KEY,
            expected_key_id="release-key-2026",
            expected_payload_sha256=str(envelope["payload_sha256"]),
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["payload"], payload)

    def test_tampered_unsupported_unsigned_and_mismatched_fail(self) -> None:
        envelope = sign_attestation({"value": 1}, key=KEY, key_id="key-a")
        cases = []
        tampered = copy.deepcopy(envelope)
        tampered["payload"]["value"] = 2  # type: ignore[index]
        cases.append(tampered)
        unsupported = copy.deepcopy(envelope)
        unsupported["algorithm"] = "unknown"
        cases.append(unsupported)
        mismatched = copy.deepcopy(envelope)
        mismatched["key_id"] = "key-b"
        cases.append(mismatched)
        for value in cases:
            with self.subTest(value=value):
                self.assertFalse(
                    verify_attestation(
                        value, key=KEY, expected_key_id="key-a"
                    )["valid"]
                )
        self.assertFalse(verify_attestation({"value": 1}, key=KEY)["valid"])
        self.assertTrue(
            verify_attestation(
                {"value": 1}, key=None, require_signed=False
            )["valid"]
        )

    def test_cli_signs_and_verifies_without_exposing_key_material(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload_path = root / "payload.json"
            key_path = root / "key"
            attestation_path = root / "attestation.json"
            payload_path.write_text('{"value": 1}\n', encoding="utf-8")
            key_path.write_bytes(KEY)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                sign_exit = main(
                    [
                        "provenance",
                        "sign",
                        str(payload_path),
                        str(attestation_path),
                        "--key-file",
                        str(key_path),
                        "--key-id",
                        "test-key",
                        "--json",
                    ]
                )
            self.assertEqual(sign_exit, 0, output.getvalue())
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                verify_exit = main(
                    [
                        "provenance",
                        "verify",
                        str(attestation_path),
                        "--key-file",
                        str(key_path),
                        "--expected-key-id",
                        "test-key",
                        "--json",
                    ]
                )
            self.assertEqual(verify_exit, 0, output.getvalue())
            self.assertTrue(json.loads(output.getvalue())["valid"])


class EvidenceDashboardTests(unittest.TestCase):
    def test_dashboard_is_stable_stratified_and_preserves_negative_result(self) -> None:
        first = generate_dashboard((ARTIFACTS,))
        second = generate_dashboard((ARTIFACTS,))

        self.assertEqual(first, second)
        self.assertEqual(first, json.loads(DASHBOARD.read_text(encoding="utf-8")))
        self.assertTrue(first["verified_artifact_inputs"])
        self.assertIn("does not establish", first["non_claim"])
        entry = first["entries"][0]
        self.assertEqual(entry["artifact_count"], 18)
        self.assertEqual(entry["complete_pair_count"], 9)
        task = entry["report"]["tasks"]["artifact-run-status"]
        self.assertGreater(
            task["sigmap"]["medians"]["input_tokens"],
            task["raw"]["medians"]["input_tokens"],
        )


if __name__ == "__main__":
    unittest.main()
