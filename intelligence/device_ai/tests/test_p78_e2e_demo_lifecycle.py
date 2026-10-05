"""P7.8 — deterministic E2E demonstration test.

Mirrors `scripts/demo/run_demo.py` exactly, step for step, but through
FastAPI's `TestClient` (in-process, no live server/Docker required) so this
same real, complete lifecycle is verified on every test run, not just when
someone happens to run the interactive demo script by hand:

    register -> confirm -> finalize -> enrich -> generate passport
    -> verify passport -> local trust anchor -> external trust anchor
    -> verify full trust -> read-back (the "consumer query" read path)

Every call goes through the real HTTP routes (not service internals), the
same way `scripts/demo/run_demo.py` does — this is the automated,
CI-runnable half of the demo story; the script is the interactive half.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _register(
    client: TestClient, png_bytes: bytes, capture_id: str = "ecotrace-demo-e2e"
) -> str:
    response = client.post(
        "/devices/register",
        files=[("images", ("demo.png", png_bytes, "image/png"))],
        data={"capture_id": capture_id},
    )
    assert response.status_code == 200, response.text
    devices = response.json()["devices"]
    assert len(devices) >= 1
    return devices[0]["device_id"]


def test_full_device_lifecycle_via_http_api(
    client: TestClient, png_bytes: bytes
) -> None:
    """The complete P7.8 demo workflow, step by step, all real HTTP calls."""
    # 1. Register
    device_id = _register(client, png_bytes)

    # 2. Confirm (DETECTED -> CONFIRMED)
    confirm_res = client.post(f"/devices/{device_id}/confirm")
    assert confirm_res.status_code == 200
    assert confirm_res.json()["current_state"] == "CONFIRMED"

    # 3. Finalize (CONFIRMED -> REGISTERED)
    finalize_res = client.post(f"/devices/{device_id}/finalize")
    assert finalize_res.status_code == 200
    assert finalize_res.json()["current_state"] == "REGISTERED"

    # 4. Enrich
    enrich_res = client.post(
        f"/devices/{device_id}/enrich", json={"ocr_text": "EcoTrace Demo Model X1"}
    )
    assert enrich_res.status_code == 200
    carbon_score = enrich_res.json()["intelligence"]["carbon"]["carbon_score"]
    assert carbon_score is not None

    # 5. Generate passport
    passport_res = client.get(f"/devices/{device_id}/passport")
    assert passport_res.status_code == 200
    passport = passport_res.json()["passport"]
    assert passport["device_id"] == device_id
    assert passport["lifecycle"]["is_registered"] is True
    assert passport["lifecycle"]["is_enriched"] is True

    # 6. Verify passport (local)
    verify_res = client.get(f"/devices/{device_id}/passport/verify")
    assert verify_res.status_code == 200
    verification = verify_res.json()["verification"]
    assert verification["verification_status"] == "VERIFIED"
    fingerprint = verification["passport_fingerprint"]
    # sha256 hex (64 chars), or 65 with an optional algo-prefix character
    assert len(fingerprint) in (64, 65)

    # 7. Local trust anchor
    local_anchor_res = client.post(f"/devices/{device_id}/passport/anchor")
    assert local_anchor_res.status_code in (200, 201)
    local_anchor = local_anchor_res.json()["anchor"]
    assert local_anchor["status"] == "ANCHORED"
    assert local_anchor["passport_fingerprint"] == fingerprint

    # 8. External (blockchain-abstraction) trust anchor — MOCKED (in-memory
    # external ledger), never a live Fabric peer in this test environment.
    external_anchor_res = client.post(f"/devices/{device_id}/passport/external-anchor")
    assert external_anchor_res.status_code == 201
    external_anchor = external_anchor_res.json()["anchor"]
    assert external_anchor["status"] == "ANCHORED"
    assert external_anchor["passport_fingerprint"] == fingerprint

    # 9. Verify full trust status
    full_trust_res = client.get(f"/devices/{device_id}/trust/full")
    assert full_trust_res.status_code == 200
    full_trust = full_trust_res.json()["trust"]
    assert full_trust["local_status"] == "VERIFIED"
    assert full_trust["external_status"] == "VERIFIED"
    assert full_trust["overall_status"] == "VERIFIED"

    # 10. Read-back — the "consumer query" read path (no dedicated consumer
    # endpoint exists; GET /devices/{id} is the actual public read path).
    readback_res = client.get(f"/devices/{device_id}")
    assert readback_res.status_code == 200
    assert readback_res.json()["device_id"] == device_id


def test_registering_the_same_capture_twice_is_rejected_not_duplicated(
    client: TestClient, png_bytes: bytes
) -> None:
    """Device IDs are derived deterministically from (capture_id, detection),
    not randomly assigned — re-registering the identical capture_id with the
    identical image is correctly rejected as a duplicate rather than silently
    creating a second record. Demonstrates why `scripts/demo/run_demo.py`'s
    `--reset` (restarting the in-memory store) is the correct way to run the
    demo repeatedly with the same fixed capture_id, not just re-running the
    script — see scripts/demo/README.md."""
    _register(client, png_bytes, capture_id="ecotrace-demo-dup")

    duplicate_response = client.post(
        "/devices/register",
        files=[("images", ("demo.png", png_bytes, "image/png"))],
        data={"capture_id": "ecotrace-demo-dup"},
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["error"]["code"] == "DUPLICATE_DEVICE"


def test_distinct_capture_ids_produce_distinct_devices(
    client: TestClient, png_bytes: bytes
) -> None:
    """A different capture_id (a different demo/session) gets its own device_id."""
    first_id = _register(client, png_bytes, capture_id="ecotrace-demo-a")
    second_id = _register(client, png_bytes, capture_id="ecotrace-demo-b")
    assert first_id != second_id
