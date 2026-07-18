import unittest

from sigmap_codex_bridge.benchmark import BenchmarkTask
from sigmap_codex_bridge.scoring import BenchmarkObservation, score_observation


class CorrectnessScoringTests(unittest.TestCase):
    def task(self) -> BenchmarkTask:
        return BenchmarkTask(
            schema_version=1,
            repository="/fixture/repo",
            revision="fixture-revision",
            prompt="Reject expired tokens",
            expected_behavior="Expired tokens fail validation",
            test_command=("python", "-m", "unittest"),
            static_check_commands=(("ruff", "check", "src"),),
            allowed_files=("src/auth.py", "tests/test_auth.py"),
            expected_files=("src/auth.py", "tests/test_auth.py"),
            expected_symbols=("validate_token",),
        )

    def test_hand_authored_correct_patch_passes_with_all_metrics(self) -> None:
        score = score_observation(
            self.task(),
            BenchmarkObservation(
                test_passed=True,
                static_check_results=(True,),
                changed_files=("src/auth.py", "tests/test_auth.py"),
                touched_symbols=("validate_token",),
                lines_added=14,
                lines_deleted=3,
                runtime_seconds=12.5,
                input_tokens=100,
                cached_input_tokens=40,
                output_tokens=20,
                tool_events=2,
                command_events=4,
            ),
        )

        self.assertTrue(score.passed)
        self.assertTrue(score.static_checks_passed)
        self.assertEqual(score.target_file_precision, 1.0)
        self.assertEqual(score.target_file_recall, 1.0)
        self.assertEqual(score.target_symbol_recall, 1.0)
        self.assertEqual(score.unexpected_files, ())
        self.assertEqual(score.patch_lines, 17)
        self.assertEqual(score.cached_input_tokens, 40)
        self.assertEqual(score.command_events, 4)

    def test_plausible_wrong_patch_fails_and_exposes_secondary_signals(self) -> None:
        score = score_observation(
            self.task(),
            BenchmarkObservation(
                test_passed=False,
                static_check_results=(False,),
                changed_files=("src/auth.py", "src/config.py"),
                touched_symbols=("parse_config",),
                lines_added=30,
                lines_deleted=1,
            ),
        )

        self.assertFalse(score.passed)
        self.assertFalse(score.static_checks_passed)
        self.assertEqual(score.target_file_precision, 0.5)
        self.assertEqual(score.target_file_recall, 0.5)
        self.assertEqual(score.target_symbol_recall, 0.0)
        self.assertEqual(score.unexpected_files, ("src/config.py",))

    def test_observation_contract_has_no_context_ground_truth_field(self) -> None:
        fields = BenchmarkObservation.__dataclass_fields__
        self.assertNotIn("context", fields)
        self.assertNotIn("sigmap_context", fields)
        self.assertNotIn("retrieval_relevance", fields)


if __name__ == "__main__":
    unittest.main()
