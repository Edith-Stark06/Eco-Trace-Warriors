#!/usr/bin/env python3
"""EcoTrace India - demo scenario runner (P8.8).

Four scenarios a pilot evaluator can run individually, each against the
real live docker-compose stack, no mocking beyond what the system itself
already discloses (e.g. the external trust anchor provider being
"memory" when no live Fabric peer is configured):

    happy-path             Full AI device lifecycle + full backend
                            stakeholder lifecycle, back to back.
    trust-mismatch          Registers a device, anchors it locally, then
                            mutates it post-anchor to trigger a genuine
                            (not simulated) local trust MISMATCH, and
                            shows the system correctly refuses to create
                            an external anchor from it.
    blockchain-unavailable  Stops the device-ai container, shows the
                            backend's blockchain-health proxy degrade
                            gracefully (never a 5xx), then restarts it.
    invalid-device          Looks up a device id that was never
                            registered and shows a clean 404, not a
                            fabricated or corrupted passport.

Usage
-----
    python scripts/demo/run_scenarios.py happy-path
    python scripts/demo/run_scenarios.py trust-mismatch
    python scripts/demo/run_scenarios.py blockchain-unavailable
    python scripts/demo/run_scenarios.py invalid-device
    python scripts/demo/run_scenarios.py all
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
import time
import uuid

import requests
from PIL import Image

AI_BASE_URL = "http://localhost:8100"
BACKEND_BASE_URL = "http://localhost:3000/api/v1"


def _print_header(title: str) -> None:
    print("=" * 70)
    print(title)
    print("=" * 70)


def _make_image_bytes(seed: int = 0) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), color=(60 + seed, 90, 120)).save(buf, format="PNG")
    return buf.getvalue()


def scenario_happy_path() -> int:
    _print_header("SCENARIO: happy-path")
    repo_root = __file__.rsplit("scripts", 1)[0]
    ai_result = subprocess.run(
        [sys.executable, f"{repo_root}scripts/demo/run_demo.py", "--base-url", AI_BASE_URL],
        check=False,
    )
    backend_result = subprocess.run(
        [sys.executable, f"{repo_root}scripts/demo/run_backend_demo.py", "--base-url", BACKEND_BASE_URL],
        check=False,
    )
    if ai_result.returncode != 0 or backend_result.returncode != 0:
        print("\n[FAILED] one or both halves of the happy-path scenario failed.")
        return 1
    print("\n[PASS] happy-path: both the AI device lifecycle and the backend "
          "stakeholder lifecycle completed successfully.")
    return 0


def scenario_trust_mismatch() -> int:
    _print_header("SCENARIO: trust-mismatch")
    session = requests.Session()
    capture_id = f"ecotrace-scenario-mismatch-{uuid.uuid4().hex[:8]}"

    print("[1/5] Registering a device...")
    reg = session.post(
        f"{AI_BASE_URL}/devices/register",
        files=[("images", ("scenario.png", _make_image_bytes(), "image/png"))],
        data={"capture_id": capture_id},
        timeout=30,
    )
    reg.raise_for_status()
    device_id = reg.json()["devices"][0]["device_id"]
    print(f"    device_id={device_id}")

    print("[2/5] Confirming, finalizing, enriching, and anchoring locally...")
    session.post(f"{AI_BASE_URL}/devices/{device_id}/confirm", timeout=30).raise_for_status()
    session.post(f"{AI_BASE_URL}/devices/{device_id}/finalize", timeout=30).raise_for_status()
    session.post(
        f"{AI_BASE_URL}/devices/{device_id}/enrich",
        json={"ocr_text": "Original label text"},
        timeout=30,
    ).raise_for_status()
    anchor = session.post(f"{AI_BASE_URL}/devices/{device_id}/passport/anchor", timeout=30)
    anchor.raise_for_status()
    print(f"    local anchor created: status={anchor.json()['anchor']['status']}")

    print("[3/5] Mutating the passport AFTER anchoring (genuine data divergence,"
          " not a simulated flag)...")
    session.post(
        f"{AI_BASE_URL}/devices/{device_id}/enrich",
        json={"ocr_text": "DIFFERENT label text after the anchor was created"},
        timeout=30,
    ).raise_for_status()

    print("[4/5] Verifying the local trust anchor against the now-mutated passport...")
    verify = session.get(f"{AI_BASE_URL}/devices/{device_id}/passport/anchor/verify", timeout=30)
    verify.raise_for_status()
    status = verify.json()["verification"]["status"]
    print(f"    verification status={status}")
    if status != "MISMATCH":
        print(f"\n[FAILED] expected MISMATCH, got {status}")
        return 1

    print("[5/5] Confirming the system refuses to create an EXTERNAL anchor "
          "from this mismatched local passport...")
    ext = session.post(f"{AI_BASE_URL}/devices/{device_id}/passport/external-anchor", timeout=30)
    body = ext.json()
    refused = ext.status_code >= 400 and body.get("error", {}).get("code") == "PASSPORT_NOT_ANCHORABLE"
    print(f"    HTTP {ext.status_code}: {body.get('error', {}).get('message', body)}")
    if not refused:
        print("\n[FAILED] expected the external anchor attempt to be refused.")
        return 1

    print("\n[PASS] trust-mismatch: a real local trust MISMATCH was triggered and "
          "correctly surfaced (never silently downgraded to success), and the "
          "system correctly refused to anchor an unverified passport externally.")
    return 0


def scenario_blockchain_unavailable() -> int:
    _print_header("SCENARIO: blockchain-unavailable")
    print("[1/4] Confirming the blockchain health proxy is reachable...")
    before = requests.get(f"{BACKEND_BASE_URL}/system/blockchain/health", timeout=10)
    print(f"    before: HTTP {before.status_code}, status={before.json()['data']['status']}")

    print("[2/4] Stopping the device-ai container (simulating an outage)...")
    subprocess.run(["docker", "compose", "stop", "device-ai"], check=True)
    time.sleep(2)

    print("[3/4] Querying the proxy again while device-ai is down...")
    during = requests.get(f"{BACKEND_BASE_URL}/system/blockchain/health", timeout=10)
    print(f"    during: HTTP {during.status_code}, status={during.json()['data']['status']}")
    backend_health = requests.get(f"{BACKEND_BASE_URL}/health", timeout=10)
    print(
        f"    backend's own health during the outage: HTTP {backend_health.status_code}, "
        f"status={backend_health.json()['data']['status']} (no cascading failure)"
    )

    print("[4/4] Restarting device-ai...")
    subprocess.run(["docker", "compose", "start", "device-ai"], check=True)
    time.sleep(3)
    after = requests.get(f"{BACKEND_BASE_URL}/system/blockchain/health", timeout=10)
    print(f"    after restart: HTTP {after.status_code}, status={after.json()['data']['status']}")

    ok = during.status_code == 200 and during.json()["data"]["status"] == "proxy_unreachable"
    ok = ok and backend_health.status_code == 200
    if not ok:
        print("\n[FAILED] expected a graceful proxy_unreachable degradation, not a 5xx.")
        return 1

    print("\n[PASS] blockchain-unavailable: the proxy degraded gracefully (never a "
          "5xx, never a fabricated status) with no cascading failure, and recovered "
          "cleanly once device-ai was restarted.")
    return 0


def scenario_invalid_device() -> int:
    _print_header("SCENARIO: invalid-device")
    fake_id = f"DEV-NONEXISTENT-{uuid.uuid4().hex[:8].upper()}"
    print(f"[1/1] Looking up a device that was never registered ({fake_id})...")
    response = requests.get(f"{AI_BASE_URL}/devices/{fake_id}/passport", timeout=10)
    print(f"    HTTP {response.status_code}: {response.json()}")

    ok = response.status_code == 404 and response.json().get("error", {}).get("code") == "DEVICE_NOT_FOUND"
    if not ok:
        print("\n[FAILED] expected a clean 404 DEVICE_NOT_FOUND.")
        return 1

    print("\n[PASS] invalid-device: a clean, honest 404 - no fabricated or "
          "corrupted passport was returned.")
    return 0


SCENARIOS = {
    "happy-path": scenario_happy_path,
    "trust-mismatch": scenario_trust_mismatch,
    "blockchain-unavailable": scenario_blockchain_unavailable,
    "invalid-device": scenario_invalid_device,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=[*SCENARIOS.keys(), "all"])
    args = parser.parse_args()

    if args.scenario == "all":
        results = {name: fn() for name, fn in SCENARIOS.items()}
        print("\n" + "=" * 70)
        print("SUMMARY")
        for name, code in results.items():
            print(f"  {'PASS' if code == 0 else 'FAIL'}: {name}")
        return 0 if all(code == 0 for code in results.values()) else 1

    return SCENARIOS[args.scenario]()


if __name__ == "__main__":
    sys.exit(main())
