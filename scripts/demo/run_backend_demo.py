#!/usr/bin/env python3
"""EcoTrace India - backend stakeholder lifecycle demonstration (P8.8).

Walks the real, complete submission lifecycle over the Node backend's
actual HTTP API using the seeded demo role accounts
(`backend/prisma/seed.ts`), exactly the way a Consumer, Collector, Admin,
and Recycler genuinely would - no service internals are called directly:

    Consumer creates a submission
    -> Admin assigns a Collector
    -> Collector accepts -> starts -> completes the pickup
    -> Admin assigns a Recycler
    -> Recycler starts -> completes recycling (reward auto-issued)
    -> Consumer verifies their own submission (the QR-scan-equivalent read)
    -> Admin + Government view the full audit trail

Prerequisites
-------------
The full docker-compose stack must already be running and healthy - see
`python scripts/demo/health_check.py`. The 5 demo role accounts must be
seeded (`docker compose exec backend npx prisma db seed`, idempotent -
safe to re-run).

Safety: demo data isolation
----------------------------
Every submission this script creates is tagged with a description
starting "EcoTrace Demo - ", so it is trivially identifiable and can be
cleanly removed with `--reset` without touching any other submission in
the database.

Usage
-----
    python scripts/demo/run_backend_demo.py
    python scripts/demo/run_backend_demo.py --base-url http://localhost:3000/api/v1
    python scripts/demo/run_backend_demo.py --reset   # delete every demo-tagged submission
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any

import requests

DEFAULT_BASE_URL = "http://localhost:3000/api/v1"
DEFAULT_TIMEOUT = 30.0
DEMO_PASSWORD = "Admin@123"  # nosec: documented, safe seed-fixture password (backend/prisma/seed.ts)
DEMO_TAG = "EcoTrace Demo"

DEMO_ACCOUNTS = {
    "admin": "admin@ecotrace.com",
    "government": "government@ecotrace.com",
    "collector": "collector@ecotrace.com",
    "recycler": "recycler@ecotrace.com",
    "consumer": "consumer@ecotrace.com",
}


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str


class DemoClient:
    """Thin wrapper over the real backend HTTP API. No shortcuts, no mocks."""

    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.tokens: dict[str, str] = {}
        self.user_ids: dict[str, str] = {}

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def login_all(self) -> None:
        for role, email in DEMO_ACCOUNTS.items():
            response = self.session.post(
                self._url("/auth/login"),
                json={"email": email, "password": DEMO_PASSWORD},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()["data"]
            self.tokens[role] = data["accessToken"]
            self.user_ids[role] = data["user"]["id"]

    def _auth_headers(self, role: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[role]}"}

    def create_submission(self) -> dict[str, Any]:
        body = {
            "category": "LAPTOP",
            "description": f"{DEMO_TAG} - dell laptop, screen cracked",
            "estimatedWeight": 2.3,
            "address": "12 MG Road, Chennai",
            "latitude": 13.0827,
            "longitude": 80.2707,
        }
        response = self.session.post(
            self._url("/submissions"), json=body, headers=self._auth_headers("consumer"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["data"]

    def assign_collector(self, submission_id: str) -> dict[str, Any]:
        response = self.session.patch(
            self._url(f"/submissions/{submission_id}/assign"),
            json={"collectorId": self.user_ids["collector"]},
            headers=self._auth_headers("admin"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["data"]

    def collector_step(self, submission_id: str, action: str) -> dict[str, Any]:
        response = self.session.patch(
            self._url(f"/submissions/{submission_id}/{action}"),
            headers=self._auth_headers("collector"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["data"]

    def assign_recycler(self, submission_id: str) -> dict[str, Any]:
        response = self.session.patch(
            self._url(f"/submissions/{submission_id}/assign-recycler"),
            json={"recyclerId": self.user_ids["recycler"]},
            headers=self._auth_headers("admin"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["data"]

    def recycler_start(self, submission_id: str) -> dict[str, Any]:
        response = self.session.patch(
            self._url(f"/submissions/{submission_id}/recycle/start"),
            headers=self._auth_headers("recycler"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["data"]

    def recycler_complete(self, submission_id: str) -> dict[str, Any]:
        body = {
            "recoveredWeight": 2.1,
            "recyclerNotes": f"{DEMO_TAG} - recovered copper/aluminum/plastic",
            "materialRecovery": {"copper": 0.6, "aluminum": 0.4, "plastic": 1.1},
        }
        response = self.session.patch(
            self._url(f"/submissions/{submission_id}/recycle/complete"),
            json=body,
            headers=self._auth_headers("recycler"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["data"]

    def consumer_view(self, submission_id: str) -> dict[str, Any]:
        response = self.session.get(
            self._url(f"/submissions/{submission_id}"),
            headers=self._auth_headers("consumer"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["data"]

    def audit_list(self, role: str) -> list[dict[str, Any]]:
        response = self.session.get(
            self._url("/submissions?limit=100"),
            headers=self._auth_headers(role),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["data"]

    def reward_balance(self) -> dict[str, Any]:
        response = self.session.get(
            self._url("/rewards/balance"), headers=self._auth_headers("consumer"), timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()["data"]


def _print_step(index: int, total: int, name: str) -> None:
    print(f"\n[{index}/{total}] {name}")


def run_demo(base_url: str, timeout: float) -> int:
    client = DemoClient(base_url, timeout)
    steps: list[StepResult] = []
    total_steps = 9

    print("=" * 70)
    print("EcoTrace India - Backend Stakeholder Lifecycle Demonstration")
    print(f"Target: {base_url}")
    print("=" * 70)

    try:
        _print_step(1, total_steps, "Logging in as all 5 demo role accounts")
        client.login_all()
        print(f"    logged in: {', '.join(DEMO_ACCOUNTS.keys())}")
        steps.append(StepResult("login", True, "5/5"))

        _print_step(2, total_steps, "Consumer creates a submission (PENDING)")
        submission = client.create_submission()
        submission_id = submission["id"]
        print(f"    submission_id={submission_id} status={submission['status']}")
        steps.append(StepResult("create", True, submission_id))

        _print_step(3, total_steps, "Admin assigns a Collector (PENDING -> ASSIGNED)")
        submission = client.assign_collector(submission_id)
        print(f"    status={submission['status']}")
        steps.append(StepResult("assign_collector", True, submission["status"]))

        _print_step(4, total_steps, "Collector accepts -> starts -> completes the pickup")
        for action in ("accept", "start", "complete"):
            submission = client.collector_step(submission_id, action)
            print(f"    {action}: status={submission['status']}")
        steps.append(StepResult("collector_workflow", True, submission["status"]))

        _print_step(5, total_steps, "Admin assigns a Recycler")
        submission = client.assign_recycler(submission_id)
        print(f"    status={submission['status']} assignedRecyclerId={submission['assignedRecyclerId']}")
        steps.append(StepResult("assign_recycler", True, submission["status"]))

        _print_step(6, total_steps, "Recycler starts -> completes recycling (reward auto-issued)")
        client.recycler_start(submission_id)
        result = client.recycler_complete(submission_id)
        completed = result["submission"]
        reward = result["reward"]
        print(f"    status={completed['status']} recoveredWeight={completed['recoveredWeight']}kg")
        print(
            f"    reward: greenCoinsAwarded={reward['greenCoinsAwarded']} "
            f"updatedBalance={reward['updatedBalance']} co2Saved={reward['sustainability']['co2Saved']}kg"
        )
        steps.append(StepResult("recycle_complete", True, completed["status"]))

        _print_step(7, total_steps, "Consumer verifies their own submission (QR-scan-equivalent read)")
        readback = client.consumer_view(submission_id)
        print(f"    status={readback['status']} materialRecovery={readback['materialRecovery']}")
        steps.append(StepResult("consumer_view", True, readback["status"]))

        _print_step(8, total_steps, "Admin + Government view the audit trail (all submissions)")
        admin_list = client.audit_list("admin")
        gov_list = client.audit_list("government")
        print(f"    admin sees {len(admin_list)} submissions, government sees {len(gov_list)} submissions")
        steps.append(StepResult("audit_trail", True, f"{len(admin_list)}/{len(gov_list)}"))

        _print_step(9, total_steps, "Consumer checks reward balance")
        balance = client.reward_balance()
        print(f"    greenCoins={balance['greenCoins']} totalCO2Saved={balance['totalCO2Saved']}kg")
        steps.append(StepResult("reward_balance", True, str(balance["greenCoins"])))

    except requests.exceptions.RequestException as exc:
        print(f"\n[FAILED] HTTP error: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 - top-level demo error boundary
        print(f"\n[FAILED] {exc}")
        return 1

    print("\n" + "=" * 70)
    print(f"Demo complete - {len(steps)}/{total_steps} steps succeeded.")
    print("=" * 70)
    print(
        "\nNOTE - honestly disclosed scope: this demonstrates the real, working "
        "Submission lifecycle end-to-end against the real backend + Postgres. "
        "It is architecturally separate from the AI device-intelligence lifecycle "
        "(scripts/demo/run_demo.py) - see reports/P6_5_BACKEND_BLOCKCHAIN_INTEGRATION.md "
        "and reports/P8_5_COMPLETE_E2E.md for why."
    )
    return 0


def reset_demo_data(base_url: str, timeout: float) -> int:
    """Delete every demo-tagged submission that is safe to delete.

    A submission that reached RECYCLED already has an issued
    RewardTransaction referencing it - the database's own foreign-key
    constraint correctly refuses to delete it (submission.service.ts's
    delete() has no override for this, by design: see backend/tests/unit/
    error-handler.middleware.test.ts's own "keeps unmapped Prisma codes as
    a generic 500" test for P2003, which locks in that a foreign-key
    violation is deliberately NOT given a friendly mapping). This is a
    real database integrity guarantee, not a bug in this script's target
    to work around - so terminal (RECYCLED) demo submissions are left in
    place, harmless historical data, still identifiable by their tag.
    """
    client = DemoClient(base_url, timeout)
    print("Logging in as admin to find and remove demo-tagged submissions...")
    admin_login = client.session.post(
        f"{base_url.rstrip('/')}/auth/login",
        json={"email": DEMO_ACCOUNTS["admin"], "password": DEMO_PASSWORD},
        timeout=timeout,
    )
    admin_login.raise_for_status()
    token = admin_login.json()["data"]["accessToken"]
    headers = {"Authorization": f"Bearer {token}"}

    listing = client.session.get(
        f"{base_url.rstrip('/')}/submissions?limit=100", headers=headers, timeout=timeout
    )
    listing.raise_for_status()
    all_submissions = listing.json()["data"]
    demo_tagged = [s for s in all_submissions if DEMO_TAG in (s.get("description") or "")]
    deletable = [s for s in demo_tagged if s["status"] != "RECYCLED"]
    terminal = [s for s in demo_tagged if s["status"] == "RECYCLED"]

    deleted = 0
    for sub in deletable:
        resp = client.session.delete(
            f"{base_url.rstrip('/')}/submissions/{sub['id']}", headers=headers, timeout=timeout
        )
        if resp.status_code < 300:
            deleted += 1
        else:
            print(f"  could not delete {sub['id']}: HTTP {resp.status_code}")

    print(f"Deleted {deleted}/{len(deletable)} deletable demo-tagged submissions.")
    if terminal:
        print(
            f"{len(terminal)} demo-tagged submission(s) already RECYCLED (reward issued) "
            "were left in place - cannot be deleted without violating referential "
            "integrity; harmless historical demo data, still identifiable by their tag."
        )
    print(
        f"{len(all_submissions) - len(demo_tagged)} non-demo submission(s) left untouched."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="backend API base URL")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="HTTP timeout (s)")
    parser.add_argument(
        "--reset", action="store_true", help="delete every demo-tagged submission and exit"
    )
    args = parser.parse_args()

    if args.reset:
        return reset_demo_data(args.base_url, args.timeout)

    return run_demo(args.base_url, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
