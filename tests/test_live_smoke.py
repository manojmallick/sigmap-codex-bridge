import os
import subprocess
import unittest


@unittest.skipUnless(
    os.environ.get("SIGMAP_BRIDGE_LIVE_SMOKE") == "1",
    "set SIGMAP_BRIDGE_LIVE_SMOKE=1 to check locally installed CLIs",
)
class LiveCliSmokeTests(unittest.TestCase):
    def test_cli_versions_are_available(self) -> None:
        for command in (("npx", "sigmap", "--version"), ("codex", "--version")):
            with self.subTest(command=command[0]):
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                    shell=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
