#!/usr/bin/env python3
"""EcoTrace India — reproducible end-to-end demonstration script (P7.8).

Walks the real device intelligence lifecycle against a **live**
`intelligence/device_ai` service, entirely over its actual HTTP API — no
service internals are called directly, so this exercises exactly what a
real client would:

    register -> confirm -> finalize -> enrich -> generate passport
    -> verify passport -> local trust anchor -> external trust anchor
    -> verify full trust -> list/query (the "consumer" read path)

Prerequisites
-------------
The device intelligence service must already be running and reachable —
this script does not start Docker/Postgres/anything else itself (see
scripts/demo/README.md for the one-command `docker compose up` that does).

Safety: demo data isolation
----------------------------
Every device this script creates is tagged with `capture_id="ecotrace-demo"`
so it is trivially identifiable. More importantly: unless the service is
explicitly configured with `DEVICE_BACKEND=postgres`, device records live
only in that process's memory (`DEVICE_BACKEND` defaults to `memory` — see
`intelligence/device_ai/.env.example` and `docker-compose.yml`) — demo runs
can **never** touch the real Postgres data the backend's own `Submission`
model uses (a completely different table this script never queries).
Resetting demo data is therefore just restarting the device-ai process/
container — see `--reset` below and scripts/demo/README.md.

Usage
-----
    python scripts/demo/run_demo.py                    # run the full demo
    python scripts/demo/run_demo.py --base-url http://localhost:8100
    python scripts/demo/run_demo.py --reset             # print/perform reset instructions
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import uuid
from dataclasses import dataclass
from typing import Any

import requests

# Device IDs are derived deterministically from (capture_id, detection) —
# NOT randomly assigned (see intelligence/device_ai/devices/service.py:
# register_from_images) — so re-registering the identical capture_id twice
# is correctly rejected as DUPLICATE_DEVICE rather than silently creating a
# second record (verified by
# tests/test_p78_e2e_demo_lifecycle.py::test_registering_the_same_capture_twice_is_rejected_not_duplicated).
# A short random suffix keeps every run distinct without needing --reset
# between runs, while the stable "ecotrace-demo-" prefix keeps every run
# identifiable as demo data.
DEMO_CAPTURE_ID = f"ecotrace-demo-{uuid.uuid4().hex[:8]}"
DEFAULT_BASE_URL = "http://localhost:8100"
DEFAULT_TIMEOUT = 30.0


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str


def _make_demo_image_bytes() -> bytes:
    """Return a small, deterministic PNG — no external asset file needed."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (256, 256), color=(90, 110, 140)).save(buf, format="PNG")
    return buf.getvalue()


class DemoClient:
    """Thin wrapper over the real device_ai HTTP API. No shortcuts, no mocks."""

    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def health(self) -> dict[str, Any]:
        response = self.session.get(self._url("/health"), timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def register(self) -> dict[str, Any]:
        files = [("images", ("demo_device.png", _make_demo_image_bytes(), "image/png"))]
        response = self.session.post(
            self._url("/devices/register"),
            files=files,
            data={"capture_id": DEMO_CAPTURE_ID},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def confirm(self, device_id: str) -> dict[str, Any]:
        response = self.session.post(
            self._url(f"/devices/{device_id}/confirm"), timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def finalize(self, device_id: str) -> dict[str, Any]:
        response = self.session.post(
            self._url(f"/devices/{device_id}/finalize"), timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def enrich(self, device_id: str) -> dict[str, Any]:
        response = self.session.post(
            self._url(f"/devices/{device_id}/enrich"),
            json={"ocr_text": "EcoTrace Demo Model X1"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_passport(self, device_id: str) -> dict[str, Any]:
        response = self.session.get(
            self._url(f"/devices/{device_id}/passport"), timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def verify_passport(self, device_id: str) -> dict[str, Any]:
        response = self.session.get(
            self._url(f"/devices/{device_id}/passport/verify"), timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def anchor_local(self, device_id: str) -> dict[str, Any]:
        response = self.session.post(
            self._url(f"/devices/{device_id}/passport/anchor"), timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def anchor_external(self, device_id: str) -> dict[str, Any]:
        response = self.session.post(
            self._url(f"/devices/{device_id}/passport/external-anchor"), timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def full_trust(self, device_id: str) -> dict[str, Any]:
        response = self.session.get(
            self._url(f"/devices/{device_id}/trust/full"), timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def get_device(self, device_id: str) -> dict[str, Any]:
        response = self.session.get(self._url(f"/devices/{device_id}"), timeout=self.timeout)
        response.raise_for_status()
        return response.json()


def _print_step(index: int, total: int, name: str) -> None:
    print(f"\n[{index}/{total}] {name}")


def _print_result(result: dict[str, Any], keys: list[str]) -> None:
    subset = {k: result.get(k) for k in keys if k in result}
    print(f"    {json.dumps(subset, indent=2, default=str)}")


def run_demo(base_url: str, timeout: float) -> int:
    client = DemoClient(base_url, timeout)
    steps: list[StepResult] = []
    total_steps = 10

    print("=" * 70)
    print("EcoTrace India - End-to-End Device Lifecycle Demonstration")
    print(f"Target: {base_url}")
    print("=" * 70)

    try:
        _print_step(1, total_steps, "Checking service health")
        health = client.health()
        print(f"    status={health.get('status')} inference_mode={health.get('inference_mode')}")
        steps.append(StepResult("health", True, health.get("status", "")))

        _print_step(2, total_steps, "Registering a device from a capture")
        reg = client.register()
        devices = reg.get("devices", [])
        if not devices:
            raise RuntimeError("Registration returned no devices - nothing to demo.")
        device_id = devices[0]["device_id"]
        print(f"    device_id={device_id} device_type={devices[0].get('device_type')}")
        steps.append(StepResult("register", True, device_id))

        _print_step(3, total_steps, "Confirming the device (DETECTED -> CONFIRMED)")
        confirmed = client.confirm(device_id)
        _print_result(confirmed, ["current_state"])
        steps.append(StepResult("confirm", True, confirmed.get("current_state", "")))

        _print_step(4, total_steps, "Finalizing registration (CONFIRMED -> REGISTERED)")
        finalized = client.finalize(device_id)
        _print_result(finalized, ["current_state"])
        steps.append(StepResult("finalize", True, finalized.get("current_state", "")))

        _print_step(5, total_steps, "Enriching with device intelligence (brand/condition/material/carbon)")
        enriched = client.enrich(device_id)
        carbon_score = enriched.get("intelligence", {}).get("carbon", {}).get("carbon_score")
        print(f"    carbon_score={carbon_score}")
        steps.append(StepResult("enrich", True, "enriched"))

        _print_step(6, total_steps, "Generating the Device Passport")
        passport = client.get_passport(device_id).get("passport", {})
        eco_id = passport.get("eco_id", "")
        carbon = passport.get("carbon", {}).get("carbon_score")
        print(f"    eco_id={eco_id} carbon_score={carbon}")
        steps.append(StepResult("passport", True, eco_id))

        _print_step(7, total_steps, "Verifying the Device Passport (local)")
        verification = client.verify_passport(device_id).get("verification", {})
        fingerprint = verification.get("passport_fingerprint", "")
        print(
            f"    verification_status={verification.get('verification_status')} "
            f"fingerprint={fingerprint[:16]}..."
        )
        steps.append(StepResult("verify_passport", True, verification.get("verification_status", "")))

        _print_step(8, total_steps, "Creating a local Trust Anchor")
        local_anchor = client.anchor_local(device_id)
        anchor_payload = local_anchor.get("anchor", {})
        print(f"    anchor_id={anchor_payload.get('anchor_id')} status={anchor_payload.get('status')}")
        steps.append(StepResult("local_anchor", True, anchor_payload.get("status", "")))

        _print_step(
            9,
            total_steps,
            "Creating an external (blockchain-abstraction) Trust Anchor "
            "- MOCKED unless FABRIC_ENABLED=true against a live peer",
        )
        external_anchor = client.anchor_external(device_id)
        ext_payload = external_anchor.get("anchor", {})
        print(f"    provider={ext_payload.get('provider')} status={ext_payload.get('status')}")
        steps.append(StepResult("external_anchor", True, ext_payload.get("status", "")))

        _print_step(10, total_steps, "Verifying full trust status + consumer-style read query")
        full_trust = client.full_trust(device_id).get("trust", {})
        print(
            f"    local={full_trust.get('local_status')} "
            f"external={full_trust.get('external_status')} "
            f"overall={full_trust.get('overall_status')}"
        )
        readback = client.get_device(device_id)
        print(f"    read-back device_id={readback.get('device_id')} (the 'consumer query' read path)")
        steps.append(StepResult("full_trust", True, full_trust.get("overall_status", "")))

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
        "\nNOTE - honestly disclosed scope: this demonstrates the real, "
        "working device intelligence lifecycle end-to-end. It does NOT "
        "demonstrate a live Hyperledger Fabric anchor (no Fabric network "
        "exists in this environment - see reports/P6_2_FABRIC_GATEWAY_INTEGRATION.md) "
        "and does NOT demonstrate a dashboard visualization of this specific "
        "device (the frontend's Submission model and this AI device-lifecycle "
        "model are architecturally disconnected - see reports/P6_5_BACKEND_BLOCKCHAIN_INTEGRATION.md "
        "and reports/P7_8_DEMO_ENVIRONMENT.md)."
    )
    return 0


def print_reset_instructions(compose_service: str) -> int:
    print(
        "Reset procedure for demo data:\n\n"
        "  Device records created by this script live only in the device-ai\n"
        "  process's memory (DEVICE_BACKEND defaults to 'memory' - see\n"
        "  intelligence/device_ai/.env.example). Restarting that one service\n"
        "  clears every demo device without touching Postgres, the backend's\n"
        "  Submission data, or anything else in the stack.\n\n"
        f"    docker compose restart {compose_service}\n\n"
        "  If not running under Docker Compose, simply restart the uvicorn\n"
        "  process (Ctrl+C, then re-run it) - the same in-memory store is\n"
        "  freshly re-created on startup.\n"
    )
    try:
        result = subprocess.run(
            ["docker", "compose", "restart", compose_service],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode == 0:
            print(f"Ran: docker compose restart {compose_service} -- succeeded.")
            return 0
        print(
            f"Attempted 'docker compose restart {compose_service}' but it did not "
            f"succeed (exit {result.returncode}): {result.stderr.strip()}\n"
            "Run the command above manually once the stack is up."
        )
        return 0
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Could not run docker compose automatically ({exc}); run the command above manually.")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="device_ai service base URL")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="HTTP timeout (s)")
    parser.add_argument(
        "--reset", action="store_true", help="print (and attempt) the demo-data reset procedure"
    )
    parser.add_argument(
        "--compose-service", default="device-ai", help="compose service name to restart on --reset"
    )
    args = parser.parse_args()

    if args.reset:
        return print_reset_instructions(args.compose_service)

    return run_demo(args.base_url, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
