"""Hash-chained bridge audit records with a tail-deletion checkpoint."""

from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping, Sequence


SCHEMA_VERSION = 1
GENESIS_HASH = "0" * 64


class AuditError(RuntimeError):
    """Raised when an audit log cannot be safely read or extended."""


@dataclass(frozen=True)
class AuditVerification:
    valid: bool
    entries: int
    head_hash: str | None = None
    error: str | None = None
    broken_sequence: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "entries": self.entries,
            "head_hash": self.head_hash,
            "error": self.error,
            "broken_sequence": self.broken_sequence,
        }


def _canonical_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _digest(value: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


class AuditLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.checkpoint_path = self.path.with_name(f"{self.path.name}.head")
        self.lock_path = self.path.with_name(f"{self.path.name}.lock")

    @contextmanager
    def _lock(self, timeout_seconds: float = 5.0) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout_seconds
        descriptor: int | None = None
        while descriptor is None:
            try:
                descriptor = os.open(
                    self.lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
                os.write(descriptor, str(os.getpid()).encode("ascii"))
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise AuditError("Timed out waiting for audit log lock")
                time.sleep(0.05)
        try:
            yield
        finally:
            os.close(descriptor)
            self.lock_path.unlink(missing_ok=True)

    def _checkpoint(self) -> dict[str, object]:
        try:
            value = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise AuditError(f"Cannot read audit checkpoint: {error}") from error
        if not isinstance(value, dict):
            raise AuditError("Audit checkpoint is not an object")
        return value

    def _write_checkpoint(self, value: Mapping[str, object]) -> None:
        temporary = self.checkpoint_path.with_name(
            f".{self.checkpoint_path.name}.{os.getpid()}.tmp"
        )
        with temporary.open("wb") as handle:
            handle.write(_canonical_bytes(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.checkpoint_path)

    def verify(self) -> AuditVerification:
        if not self.path.exists() and not self.checkpoint_path.exists():
            return AuditVerification(valid=False, entries=0, error="no audit log")
        if not self.path.exists() or not self.checkpoint_path.exists():
            return AuditVerification(
                valid=False,
                entries=0,
                error="audit log and checkpoint must both exist",
            )

        previous_hash = GENESIS_HASH
        entries = 0
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            return AuditVerification(valid=False, entries=0, error=str(error))

        for line_number, line in enumerate(lines, start=1):
            if not line:
                return AuditVerification(
                    valid=False,
                    entries=entries,
                    error="blank audit entry",
                    broken_sequence=line_number,
                )
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as error:
                return AuditVerification(
                    valid=False,
                    entries=entries,
                    error=f"invalid JSON: {error.msg}",
                    broken_sequence=line_number,
                )
            if not isinstance(entry, dict):
                return AuditVerification(
                    valid=False,
                    entries=entries,
                    error="audit entry is not an object",
                    broken_sequence=line_number,
                )

            claimed_hash = entry.pop("entry_hash", None)
            sequence = entry.get("sequence")
            if sequence != line_number:
                return AuditVerification(
                    valid=False,
                    entries=entries,
                    error="non-contiguous sequence",
                    broken_sequence=line_number,
                )
            if entry.get("previous_hash") != previous_hash:
                return AuditVerification(
                    valid=False,
                    entries=entries,
                    error="previous hash mismatch",
                    broken_sequence=line_number,
                )
            computed_hash = _digest(entry)
            if claimed_hash != computed_hash:
                return AuditVerification(
                    valid=False,
                    entries=entries,
                    error="entry hash mismatch",
                    broken_sequence=line_number,
                )
            previous_hash = computed_hash
            entries += 1

        try:
            checkpoint = self._checkpoint()
        except AuditError as error:
            return AuditVerification(valid=False, entries=entries, error=str(error))
        if checkpoint.get("schema_version") != SCHEMA_VERSION:
            return AuditVerification(
                valid=False, entries=entries, error="checkpoint schema mismatch"
            )
        if checkpoint.get("entries") != entries:
            return AuditVerification(
                valid=False,
                entries=entries,
                head_hash=previous_hash,
                error="checkpoint entry count mismatch",
            )
        if checkpoint.get("head_hash") != previous_hash:
            return AuditVerification(
                valid=False,
                entries=entries,
                head_hash=previous_hash,
                error="checkpoint head hash mismatch",
            )
        return AuditVerification(
            valid=True,
            entries=entries,
            head_hash=previous_hash,
        )

    def record(
        self,
        *,
        run_id: str,
        base_commit: str,
        condition: str,
        context: str,
        codex_thread_id: str | None,
        exit_code: int,
        usage: Mapping[str, int],
        source_dirty: bool,
        changes: Sequence[Mapping[str, object]],
        timestamp: str | None = None,
    ) -> str:
        with self._lock():
            if self.path.exists() or self.checkpoint_path.exists():
                verification = self.verify()
                if not verification.valid:
                    raise AuditError(
                        f"Refusing to append to invalid audit chain: "
                        f"{verification.error}"
                    )
                sequence = verification.entries + 1
                previous_hash = verification.head_hash or GENESIS_HASH
            else:
                sequence = 1
                previous_hash = GENESIS_HASH

            entry: dict[str, object] = {
                "schema_version": SCHEMA_VERSION,
                "sequence": sequence,
                "timestamp": timestamp
                or datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                "run_id": run_id,
                "base_commit": base_commit,
                "condition": condition,
                "context_sha256": hashlib.sha256(context.encode("utf-8")).hexdigest(),
                "codex_thread_id": codex_thread_id,
                "exit_code": exit_code,
                "usage": dict(usage),
                "source_dirty": source_dirty,
                "changes": list(changes),
                "previous_hash": previous_hash,
            }
            entry_hash = _digest(entry)
            stored_entry = {**entry, "entry_hash": entry_hash}

            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("ab") as handle:
                handle.write(_canonical_bytes(stored_entry) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._write_checkpoint(
                {
                    "schema_version": SCHEMA_VERSION,
                    "entries": sequence,
                    "head_hash": entry_hash,
                }
            )
            return entry_hash
