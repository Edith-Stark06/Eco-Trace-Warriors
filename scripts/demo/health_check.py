#!/usr/bin/env python3
"""EcoTrace India — demo environment health check (P8.8).

Verifies every service a fresh evaluator needs is actually up and healthy
before running the demo scenarios — real HTTP calls, no assumptions from
`docker compose ps` alone (a container can report "healthy" while its own
application-level health check would still fail a stricter probe, so this
script re-checks at the HTTP layer too).

Usage:
    python scripts/demo/health_check.py
"""

from __future__ import annotations

import sys

import requests

CHECKS = [
    ("Backend (Node)", "http://localhost:3000/api/v1/health"),
    ("Device Intelligence (Python)", "http://localhost:8100/health"),
    ("Frontend (static)", "http://localhost:8080/"),
]


def main() -> int:
    print("=" * 70)
    print("EcoTrace India - Demo Environment Health Check")
    print("=" * 70)

    all_ok = True
    for name, url in CHECKS:
        try:
            response = requests.get(url, timeout=5)
            ok = response.status_code == 200
            status = "OK" if ok else f"HTTP {response.status_code}"
        except requests.exceptions.RequestException as exc:
            ok = False
            status = f"UNREACHABLE ({exc.__class__.__name__})"
        all_ok = all_ok and ok
        marker = "[PASS]" if ok else "[FAIL]"
        print(f"{marker} {name:<32} {url:<45} {status}")

    print("=" * 70)
    if all_ok:
        print("All services healthy. Ready to run scripts/demo/run_scenarios.py")
        return 0

    print(
        "One or more services are not healthy. Run `docker compose up -d --build` "
        "and wait for `docker compose ps` to show every service as healthy, then "
        "re-run this check."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
