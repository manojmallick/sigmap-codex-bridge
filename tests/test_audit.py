import json
import tempfile
import unittest
from pathlib import Path

from sigmap_codex_bridge.audit import AuditError, AuditLog


def append_record(log: AuditLog, sequence: int) -> str:
    return log.record(
        run_id=f"run-{sequence}",
        base_commit="a" * 40,
        condition="sigmap" if sequence % 2 else "raw",
        context=f"context-{sequence}",
        codex_thread_id=f"thread-{sequence}",
        exit_code=0,
        usage={"input_tokens": sequence, "output_tokens": sequence + 1},
        source_dirty=False,
        changes=[{"status": "modified", "path": "src/example.py"}],
        timestamp=f"2026-07-18T00:00:0{sequence}+00:00",
    )


class AuditLogTests(unittest.TestCase):
    def create_log(self, directory: str, entries: int = 3) -> AuditLog:
        log = AuditLog(Path(directory) / "audit.jsonl")
        for sequence in range(1, entries + 1):
            append_record(log, sequence)
        self.assertTrue(log.verify().valid)
        return log

    def test_records_full_hash_chain_without_raw_context_or_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = self.create_log(directory, entries=2)
            records = [
                json.loads(line)
                for line in log.path.read_text(encoding="utf-8").splitlines()
            ]

            self.assertEqual(len(records[0]["context_sha256"]), 64)
            self.assertEqual(len(records[0]["entry_hash"]), 64)
            self.assertEqual(records[1]["previous_hash"], records[0]["entry_hash"])
            self.assertNotIn("context", records[0])
            self.assertNotIn("task", records[0])

    def test_detects_modified_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = self.create_log(directory)
            records = log.path.read_text(encoding="utf-8").splitlines()
            value = json.loads(records[1])
            value["exit_code"] = 33
            records[1] = json.dumps(value, sort_keys=True, separators=(",", ":"))
            log.path.write_text("\n".join(records) + "\n", encoding="utf-8")

            verification = log.verify()

            self.assertFalse(verification.valid)
            self.assertEqual(verification.broken_sequence, 2)

    def test_detects_middle_and_tail_deletion(self) -> None:
        for deletion in (1, 2):
            with (
                self.subTest(deletion=deletion),
                tempfile.TemporaryDirectory() as directory,
            ):
                log = self.create_log(directory)
                records = log.path.read_text(encoding="utf-8").splitlines()
                del records[deletion]
                log.path.write_text("\n".join(records) + "\n", encoding="utf-8")

                self.assertFalse(log.verify().valid)

    def test_detects_insertion_and_reordering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = self.create_log(directory)
            original = log.path.read_text(encoding="utf-8")
            records = original.splitlines()
            records.insert(1, records[0])
            log.path.write_text("\n".join(records) + "\n", encoding="utf-8")
            self.assertFalse(log.verify().valid)

            log.path.write_text(original, encoding="utf-8")
            records = original.splitlines()
            records[0], records[1] = records[1], records[0]
            log.path.write_text("\n".join(records) + "\n", encoding="utf-8")
            self.assertFalse(log.verify().valid)

    def test_detects_missing_or_corrupt_checkpoint_and_refuses_append(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = self.create_log(directory)
            log.checkpoint_path.write_text("not-json", encoding="utf-8")

            self.assertFalse(log.verify().valid)
            with self.assertRaises(AuditError):
                append_record(log, 4)


if __name__ == "__main__":
    unittest.main()
