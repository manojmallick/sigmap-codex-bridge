"""Deterministic SigMap process fixture selected by FAKE_SIGMAP_MODE."""

import os
import sys
import time


mode = os.environ.get("FAKE_SIGMAP_MODE", "ready")
if mode == "ready":
    print("# Ranked context\nsrc/auth.py: validate_token(token)")
elif mode == "missing_index":
    print("[sigmap] no context file found. Run: sigmap", file=sys.stderr)
    raise SystemExit(1)
elif mode == "timeout":
    time.sleep(2)
elif mode == "empty":
    pass
else:
    print("synthetic SigMap failure", file=sys.stderr)
    raise SystemExit(7)
