"""Deterministic Codex JSONL process fixture selected by FAKE_CODEX_MODE."""

import json
import os
import sys
import time
from pathlib import Path


mode = os.environ.get("FAKE_CODEX_MODE", "success")
stdin_text = sys.stdin.read()

if mode == "timeout":
    time.sleep(2)
elif mode == "malformed":
    print('{"type":"thread.started","thread_id":"thread-fixture"}')
    print("not-json")
elif mode == "incomplete":
    print(json.dumps({"type": "thread.started", "thread_id": "thread-fixture"}))
elif mode == "failed":
    print(json.dumps({"type": "thread.started", "thread_id": "thread-fixture"}))
    print(json.dumps({"type": "turn.failed", "message": "synthetic failure"}))
    raise SystemExit(7)
else:
    if mode == "write":
        leaked = Path("source-only.txt").exists()
        Path("codex-created.txt").write_text("created by fixture\n", encoding="utf-8")
    else:
        leaked = False
    changed_paths = (
        [{"path": "codex-created.txt", "kind": "create"}]
        if mode == "write"
        else [
            {"path": "src/auth.py", "kind": "update"},
            {"path": "tests/test_auth.py", "kind": "create"},
        ]
    )
    events = [
        {"type": "thread.started", "thread_id": "thread-fixture"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "id": "change-1",
                "type": "file_change",
                "changes": changed_paths,
            },
        },
        {
            "type": "item.completed",
            "item": {"id": "command-1", "type": "command_execution"},
        },
        {
            "type": "item.completed",
            "item": {"id": "tool-1", "type": "mcp_tool_call"},
        },
        {
            "type": "item.completed",
            "item": {
                "id": "message-1",
                "type": "agent_message",
                "text": (
                    f"fixture completed; context={bool(stdin_text)}; leaked={leaked}"
                    if mode == "write"
                    else f"fixture completed; context={bool(stdin_text)}"
                ),
            },
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 120,
                "cached_input_tokens": 20,
                "output_tokens": 30,
                "reasoning_output_tokens": 4,
            },
        },
    ]
    for event in events:
        print(json.dumps(event))
