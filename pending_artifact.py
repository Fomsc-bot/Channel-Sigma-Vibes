#!/usr/bin/env python3
"""Emit artifact IDs needed to resume a Content Rewards pre-approval flow."""
import json
import os
import sys
from pathlib import Path

state_file = Path(__file__).resolve().parent / "content" / "content_rewards_delivery.json"
state = json.loads(state_file.read_text(encoding="utf-8-sig")) if state_file.exists() else {}
pending = next((row for row in state.values() if row.get("status") == "draft_pending"), None)
mode = sys.argv[1] if len(sys.argv) > 1 else "download"
if not pending:
    sys.exit(0)
run_id = str(pending.get("artifact_run_id", ""))
current_run = os.environ.get("GITHUB_RUN_ID", "")
if mode == "upload" and run_id != current_run:
    sys.exit(0)
if mode not in {"download", "upload"}:
    raise SystemExit("usage: pending_artifact.py [download|upload]")
print(f"run_id={run_id}")
print(f"name=content-rewards-video-{run_id}")
