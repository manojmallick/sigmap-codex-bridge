"""Machine-readable Git repository state and change capture."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .process import ProcessResult, run_process


class GitError(RuntimeError):
    """Raised when a required Git operation cannot be completed."""


@dataclass(frozen=True)
class FileChange:
    status: str
    path: str
    original_path: str | None = None
    index_status: str = "."
    worktree_status: str = "."

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class GitState:
    root: str
    base_commit: str
    dirty: bool
    changes: tuple[FileChange, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "base_commit": self.base_commit,
            "dirty": self.dirty,
            "changes": [change.to_dict() for change in self.changes],
        }


def _change_status(xy: str, *, kind: str | None = None) -> str:
    if kind == "R":
        return "renamed"
    if kind == "C":
        return "copied"
    if "D" in xy:
        return "deleted"
    if "A" in xy or "?" in xy:
        return "added"
    return "modified"


def parse_porcelain_v2_z(output: str) -> tuple[FileChange, ...]:
    """Parse ``git status --porcelain=v2 -z`` without path ambiguity."""

    records = output.split("\0")
    changes: list[FileChange] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record or record.startswith("# ") or record.startswith("! "):
            continue
        if record.startswith("? "):
            changes.append(
                FileChange(status="added", path=record[2:], index_status="?")
            )
            continue
        if record.startswith("1 "):
            fields = record.split(" ", 8)
            if len(fields) != 9:
                raise GitError("Malformed ordinary porcelain-v2 record")
            xy = fields[1]
            changes.append(
                FileChange(
                    status=_change_status(xy),
                    path=fields[8],
                    index_status=xy[0],
                    worktree_status=xy[1],
                )
            )
            continue
        if record.startswith("2 "):
            fields = record.split(" ", 9)
            if len(fields) != 10 or index >= len(records):
                raise GitError("Malformed rename/copy porcelain-v2 record")
            xy = fields[1]
            score = fields[8]
            original_path = records[index]
            index += 1
            changes.append(
                FileChange(
                    status=_change_status(xy, kind=score[:1]),
                    path=fields[9],
                    original_path=original_path,
                    index_status=xy[0],
                    worktree_status=xy[1],
                )
            )
            continue
        if record.startswith("u "):
            fields = record.split(" ", 10)
            if len(fields) != 11:
                raise GitError("Malformed unmerged porcelain-v2 record")
            xy = fields[1]
            changes.append(
                FileChange(
                    status="unmerged",
                    path=fields[10],
                    index_status=xy[0],
                    worktree_status=xy[1],
                )
            )
            continue
        raise GitError(f"Unsupported porcelain-v2 record: {record[:20]}")
    return tuple(sorted(changes, key=lambda change: (change.path, change.status)))


class GitRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()

    def _run(self, *args: str) -> ProcessResult:
        result = run_process(
            ("git", "-C", str(self.path), *args),
            cwd=self.path,
            timeout_seconds=30,
        )
        if not result.ok:
            detail = result.stderr.strip() or result.launch_error or "unknown error"
            raise GitError(f"git {' '.join(args)} failed: {detail}")
        return result

    def root(self) -> Path:
        return Path(self._run("rev-parse", "--show-toplevel").stdout.strip()).resolve()

    def base_commit(self) -> str:
        return self._run("rev-parse", "HEAD").stdout.strip()

    def changes(self) -> tuple[FileChange, ...]:
        result = self._run(
            "status",
            "--porcelain=v2",
            "--untracked-files=all",
            "-z",
        )
        return parse_porcelain_v2_z(result.stdout)

    def inspect(self) -> GitState:
        root = self.root()
        changes = self.changes()
        return GitState(
            root=str(root),
            base_commit=self.base_commit(),
            dirty=bool(changes),
            changes=changes,
        )
