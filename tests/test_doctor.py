import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

from git_helpers import initialize_repo
from sigmap_codex_bridge.cli import main
from sigmap_codex_bridge.doctor import render_doctor, run_doctor


def write_script(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def check(result, name: str):
    return next(item for item in result.checks if item.name == name)


class DoctorTests(unittest.TestCase):
    def fixtures(self, root: Path, *, stale: bool = False, auth: bool = True):
        codex = write_script(
            root / "codex.py",
            """import sys
if sys.argv[1:] == ['--version']:
    print('codex-cli fixture')
elif sys.argv[1:] == ['login', 'status']:
    print('Logged in using ChatGPT')
    raise SystemExit(0 if AUTH else 1)
else:
    raise SystemExit(2)
""".replace("AUTH", "True" if auth else "False"),
        )
        freshness = "warn" if stale else "ok"
        sigmap_payload = {
            "checks": [
                {"id": "context", "status": "ok", "detail": "context exists"},
                {"id": "index", "status": "ok", "detail": "31 files indexed"},
                {
                    "id": "freshness",
                    "status": freshness,
                    "detail": "index is stale" if stale else "index is fresh",
                },
            ],
            "ok": not stale,
        }
        sigmap = write_script(
            root / "sigmap.py",
            "import json\nprint(json.dumps(" + repr(sigmap_payload) + "))\n",
        )
        return (sys.executable, str(codex)), (sys.executable, str(sigmap))

    def test_ready_environment_reports_every_live_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            initialize_repo(repo)
            codex, sigmap = self.fixtures(root)

            result = run_doctor(repo, codex_command=codex, sigmap_command=sigmap)

        self.assertTrue(result.live_ready)
        self.assertTrue(result.replay_ready)
        self.assertEqual(check(result, "python").status, "ok")
        self.assertEqual(check(result, "git_clean").status, "ok")
        self.assertEqual(check(result, "sigmap_index").status, "ok")
        self.assertEqual(check(result, "codex_auth").status, "ok")
        self.assertIn("Live readiness: READY", render_doctor(result))

    def test_missing_tools_invalid_repo_and_dirty_state_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = run_doctor(
                root,
                codex_command=("missing-codex-fixture",),
                sigmap_command=("missing-sigmap-fixture",),
            )
            repo = root / "repo"
            initialize_repo(repo)
            (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            dirty = run_doctor(
                repo,
                codex_command=("missing-codex-fixture",),
                sigmap_command=("missing-sigmap-fixture",),
            )

        self.assertEqual(check(invalid, "git_repository").status, "fail")
        self.assertEqual(check(invalid, "codex_executable").status, "fail")
        self.assertEqual(check(invalid, "sigmap_executable").status, "fail")
        self.assertEqual(check(dirty, "git_clean").status, "fail")
        self.assertFalse(dirty.live_ready)

    def test_unauthenticated_codex_and_stale_index_are_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            initialize_repo(repo)
            codex, sigmap = self.fixtures(root, stale=True, auth=False)

            result = run_doctor(repo, codex_command=codex, sigmap_command=sigmap)

        self.assertEqual(check(result, "codex_executable").status, "ok")
        self.assertEqual(check(result, "codex_auth").status, "fail")
        self.assertIn("codex login", check(result, "codex_auth").fix)
        self.assertEqual(check(result, "sigmap_index").status, "warn")
        self.assertIn("sigmap", check(result, "sigmap_index").fix)
        self.assertFalse(result.live_ready)

    def test_broken_codex_is_not_reported_as_merely_unauthenticated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            initialize_repo(repo)
            broken = write_script(
                root / "broken.py",
                "import sys\nprint('missing platform binary', file=sys.stderr)\nraise SystemExit(7)\n",
            )
            _codex, sigmap = self.fixtures(root)

            result = run_doctor(
                repo,
                codex_command=(sys.executable, str(broken)),
                sigmap_command=sigmap,
            )

        self.assertEqual(check(result, "codex_executable").status, "fail")
        self.assertIn("broken", check(result, "codex_executable").detail)
        self.assertIn("executable failed", check(result, "codex_auth").detail)

    def test_cli_can_enforce_live_readiness_without_blocking_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            arguments = [
                "doctor",
                "--repo",
                directory,
                "--codex-command",
                "missing-codex-fixture",
                "--sigmap-command",
                "missing-sigmap-fixture",
                "--json",
            ]
            with contextlib.redirect_stdout(io.StringIO()):
                advisory_exit = main(arguments)
                required_exit = main([*arguments, "--require-live"])

        self.assertEqual(advisory_exit, 0)
        self.assertEqual(required_exit, 2)


if __name__ == "__main__":
    unittest.main()
