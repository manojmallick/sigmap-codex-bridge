import subprocess
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repo), *args),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return completed.stdout.strip()


def initialize_repo(repo: Path) -> str:
    repo.mkdir(parents=True)
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Bridge Tests")
    (repo / "modified.txt").write_text("before\n", encoding="utf-8")
    (repo / "deleted.txt").write_text("delete me\n", encoding="utf-8")
    (repo / "renamed.txt").write_text("rename me\n", encoding="utf-8")
    git(repo, "add", "modified.txt", "deleted.txt", "renamed.txt")
    git(repo, "commit", "-m", "initial")
    return git(repo, "rev-parse", "HEAD")
