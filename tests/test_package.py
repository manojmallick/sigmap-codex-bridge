import os
import subprocess
import sys
import unittest
from pathlib import Path

import sigmap_codex_bridge as package


ROOT = Path(__file__).resolve().parents[1]


class PackageContractTests(unittest.TestCase):
    def test_public_exports_and_version(self) -> None:
        self.assertEqual(package.__version__, "0.6.0")
        self.assertEqual(package.__all__[0], "Bridge")
        self.assertIs(package.BridgeResult, package.__dict__["BridgeResult"])
        self.assertEqual(int(package.ExitCode.SUCCESS), 0)

    def test_module_entrypoint_exposes_cli_help(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        completed = subprocess.run(
            (sys.executable, "-m", "sigmap_codex_bridge", "--help"),
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            shell=False,
            env=env,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("sigmap-bridge", completed.stdout)
        self.assertIn("run", completed.stdout)
        self.assertIn("demo", completed.stdout)
        self.assertIn("doctor", completed.stdout)
        self.assertIn("submission", completed.stdout)


if __name__ == "__main__":
    unittest.main()
