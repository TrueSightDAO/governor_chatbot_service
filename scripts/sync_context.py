#!/usr/bin/env python3
"""Sync agentic_ai_context and related repos, then rebuild system prompt cache.

Run via cron every 15 minutes on the EC2 host:
    */15 * * * * cd /opt/governor_chatbot && python3 scripts/sync_context.py

Or manually:
    python3 scripts/sync_context.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPOS = [
    ("agentic_ai_context", "https://github.com/TrueSightDAO/agentic_ai_context.git"),
    # Add more repos as needed for codebase context:
    # ("tokenomics", "https://github.com/TrueSightDAO/tokenomics.git"),
    # ("dapp", "https://github.com/TrueSightDAO/dapp.git"),
]

DEFAULT_BASE_DIR = Path("/opt/governor_chatbot/context")


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def sync_repo(name: str, url: str, base_dir: Path) -> None:
    repo_path = base_dir / name
    if repo_path.exists():
        print(f"Pulling {name} ...")
        result = run(["git", "pull", "--ff-only"], cwd=repo_path)
        if result.returncode != 0:
            print(f"  WARN: git pull failed: {result.stderr}", file=sys.stderr)
        else:
            print(f"  OK: {result.stdout.strip()}")
    else:
        print(f"Cloning {name} ...")
        result = run(["git", "clone", "--depth", "1", url, str(repo_path)], cwd=base_dir)
        if result.returncode != 0:
            print(f"  ERROR: git clone failed: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        print(f"  OK: cloned to {repo_path}")


def main() -> int:
    base_dir = Path(os.getenv("CONTEXT_REPOS_DIR", str(DEFAULT_BASE_DIR)))
    base_dir.mkdir(parents=True, exist_ok=True)

    for name, url in REPOS:
        sync_repo(name, url, base_dir)

    # Optional: trigger prompt refresh via HTTP to the running service
    service_url = os.getenv("CHATBOT_SERVICE_URL", "http://localhost:8000")
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{service_url}/refresh-context",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=b"{}",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"Prompt refresh: {resp.read().decode()}")
    except Exception as exc:
        print(f"Prompt refresh skipped (service may be offline): {exc}", file=sys.stderr)

    print("Sync complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
