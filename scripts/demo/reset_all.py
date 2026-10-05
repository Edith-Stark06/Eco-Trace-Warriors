#!/usr/bin/env python3
"""EcoTrace India — full demo environment reset (P8.8).

Orchestrates a complete, deterministic reset of every demo surface, so an
evaluator can always get back to a clean starting point:

    1. Re-seed the 5 demo role accounts (backend/prisma/seed.ts, idempotent
       via upsert — safe to run any number of times).
    2. Delete every demo-tagged backend submission that is safe to delete
       (scripts/demo/run_backend_demo.py --reset).
    3. Restart device-ai to clear its in-memory device store
       (scripts/demo/run_demo.py --reset).

Usage
-----
    python scripts/demo/reset_all.py
"""

from __future__ import annotations

import subprocess
import sys
import time

import requests


def _run(description: str, cmd: list[str]) -> bool:
    print(f"\n--- {description} ---")
    result = subprocess.run(cmd, check=False)
    ok = result.returncode == 0
    print(f"{'OK' if ok else 'FAILED'}: {description}")
    return ok


def _wait_for_device_ai_healthy(timeout_seconds: float = 30.0) -> bool:
    """Poll device-ai's own /health until it responds, so this script hands
    back control only once the restarted container is actually ready —
    not merely once `docker compose restart` returned (which can be a few
    seconds before the process inside is serving requests again)."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            if requests.get("http://localhost:8100/health", timeout=2).status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    return False


def main() -> int:
    print("=" * 70)
    print("EcoTrace India - Full Demo Environment Reset")
    print("=" * 70)

    repo_root = __file__.rsplit("scripts", 1)[0]

    ok1 = _run(
        "Re-seeding the 5 demo role accounts",
        ["docker", "compose", "exec", "-T", "backend", "npx", "--yes", "tsx", "prisma/seed.ts"],
    )
    ok2 = _run(
        "Removing demo-tagged backend submissions",
        [sys.executable, f"{repo_root}scripts/demo/run_backend_demo.py", "--reset"],
    )
    ok3 = _run(
        "Restarting device-ai to clear its in-memory device store",
        [sys.executable, f"{repo_root}scripts/demo/run_demo.py", "--reset"],
    )
    if ok3:
        print("Waiting for device-ai to report healthy again...")
        ok3 = _wait_for_device_ai_healthy()
        print("device-ai is healthy." if ok3 else "device-ai did not become healthy in time.")

    print("\n" + "=" * 70)
    if ok1 and ok2 and ok3:
        print("Reset complete. Run `python scripts/demo/health_check.py` to confirm "
              "everything is healthy before the next demo run.")
        return 0
    print("Reset finished with at least one step reporting a failure - see above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
