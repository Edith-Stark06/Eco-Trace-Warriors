"""P7.9 — deterministic failure-injection tests for gaps not covered elsewhere.

Most resilience scenarios in the P7.9 brief are already covered by earlier
phases and are cross-referenced (not duplicated) in
`reports/P7_9_PERFORMANCE_RELIABILITY.md`: Fabric unavailable (P6.2/P6.7),
database unreachable (P7.3), duplicate requests (P7.8), stale/mismatched
trust anchors and invalid passports (P5.7-P5.9), invalid lifecycle
transitions (chaincode 45/45 + backend authorize tests), large image
uploads (`test_predict.py::test_predict_rejects_large_file`), mobile
offline/sync (P6.3's `sync_queue_repository_test.dart`).

This file covers what genuinely had zero coverage before this phase: OCR
backend failures, barcode reader failures, concurrent request safety
(exercising the P7.3 metrics registry and P7.4 rate limiter's locking under
real thread contention, not just single-threaded calls), and a genuine
Fabric RPC *timeout* (a slow-but-reachable peer, distinct from an
unreachable one — already covered).

No brittle timing assertions: thresholds are wide (an order of magnitude
above the injected delay/expected latency), matching this phase's own
"robust thresholds, not brittle" requirement — and the one place a strict
elapsed-time assertion would be tempting (the timeout test) instead asserts
on the *outcome* (the correct exception type), not a specific duration.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from device_ai.api import dependencies
from device_ai.devices.fabric_gateway_client import FabricGatewayClient
from device_ai.exceptions import FabricUnavailable
from device_ai.ocr.backends import MockOCRBackend, OCRBackend
from device_ai.ocr.barcode import BarcodeReader, MockBarcodeReader
from device_ai.ocr.models import BarcodeResult, TextSpan
from device_ai.ocr.parser import OCRParser
from device_ai.ocr.service import OCRService
from device_ai.preprocessing.image_loader import LoadedImage
from device_ai.tests.fabric_test_server import (
    FakeFabricGateway,
    FakeGatewayBehavior,
    generate_self_signed_identity,
)

from .test_p62_fabric_gateway import _fabric_settings


def _fastapi_app(client: TestClient) -> FastAPI:
    """`TestClient.app` is typed as a bare ASGI callable upstream; it is
    concretely always the `FastAPI` instance `create_app()` built. This
    narrows the type once so `.dependency_overrides` type-checks cleanly."""
    return cast(FastAPI, client.app)


# ---------------------------------------------------------------------------
# OCR backend failure
# ---------------------------------------------------------------------------


class _FailingOCRBackend(OCRBackend):
    """A configured-and-ready backend that raises during recognition —
    distinct from the already-covered "not configured" case."""

    name = "failing-ocr"

    def recognize(self, image: LoadedImage) -> list[TextSpan]:
        raise RuntimeError("simulated OCR engine crash")


def test_ocr_extract_backend_failure_returns_the_standard_error_envelope(
    client: TestClient, png_bytes: bytes
) -> None:
    """An OCR backend that raises mid-extraction must not leak an
    unhandled-exception traceback to the client — it should surface through
    the same standard error envelope every other failure uses (P7.9: OCR
    failure was previously entirely untested).

    Overrides `get_ocr_service` itself, not `get_ocr_backend`/
    `get_barcode_reader`: the real `get_ocr_service` (api/dependencies.py)
    calls those two as plain functions, not as FastAPI-resolved `Depends`
    parameters, so `app.dependency_overrides` cannot intercept them
    individually — only the outer service factory is actually overridable.
    """
    failing_service = OCRService(
        backend=_FailingOCRBackend(),
        parser=OCRParser(),
        barcode_reader=MockBarcodeReader(),
    )
    _fastapi_app(client).dependency_overrides[dependencies.get_ocr_service] = (
        lambda: failing_service
    )
    # raise_server_exceptions=False: the default True (used by the shared
    # `client` fixture) re-raises the original exception into the test even
    # after the registered handler formats a clean response — appropriate
    # for catching genuinely unhandled bugs, but this test deliberately
    # exercises that handler's own behavior, so it needs to see the
    # response, not the exception.
    no_raise_client = TestClient(_fastapi_app(client), raise_server_exceptions=False)
    try:
        response = no_raise_client.post(
            "/ocr/extract",
            files=[("images", ("device.png", png_bytes, "image/png"))],
        )
    finally:
        del _fastapi_app(client).dependency_overrides[dependencies.get_ocr_service]

    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert "error" in body
    # No raw exception text/stack trace leaked (security: matches P6.8/P7.4's
    # information-disclosure review — re-verified here under a genuine
    # failure, not just asserted from reading the handler source).
    assert "RuntimeError" not in body["error"]["message"]
    assert "simulated OCR engine crash" not in body["error"]["message"]


# ---------------------------------------------------------------------------
# Barcode reader failure
# ---------------------------------------------------------------------------


class _FailingBarcodeReader(BarcodeReader):
    """A configured reader that raises during decode."""

    name = "failing-barcode"

    def decode(self, image: LoadedImage) -> list[BarcodeResult]:
        raise RuntimeError("simulated barcode decoder crash")


def test_ocr_extract_barcode_failure_returns_the_standard_error_envelope(
    client: TestClient, png_bytes: bytes
) -> None:
    """Same guarantee as the OCR backend case, for the barcode reader."""
    failing_service = OCRService(
        backend=MockOCRBackend(),
        parser=OCRParser(),
        barcode_reader=_FailingBarcodeReader(),
    )
    _fastapi_app(client).dependency_overrides[dependencies.get_ocr_service] = (
        lambda: failing_service
    )
    no_raise_client = TestClient(_fastapi_app(client), raise_server_exceptions=False)
    try:
        response = no_raise_client.post(
            "/ocr/extract",
            files=[("images", ("device.png", png_bytes, "image/png"))],
        )
    finally:
        del _fastapi_app(client).dependency_overrides[dependencies.get_ocr_service]

    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert "RuntimeError" not in body["error"]["message"]


# ---------------------------------------------------------------------------
# Concurrent requests
# ---------------------------------------------------------------------------


def test_concurrent_health_requests_do_not_corrupt_shared_state(
    client: TestClient,
) -> None:
    """20 concurrent /health requests, all succeeding, with the shared
    process-wide metrics registry (P7.3) correctly counting every one — the
    registry's Lock is exercised under genuine thread contention here, not
    just single-threaded calls (every existing metrics test is
    single-threaded)."""
    from device_ai.utils.metrics import get_metrics_registry

    get_metrics_registry().reset()

    results: list[int] = []
    lock = threading.Lock()

    def _call() -> None:
        response = client.get("/health")
        with lock:
            results.append(response.status_code)

    threads = [threading.Thread(target=_call) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(results) == 20
    assert all(code == 200 for code in results)

    snapshot = get_metrics_registry().snapshot()
    health_entry = next(
        r for r in snapshot["requests"]["by_route"] if r["route"] == "/health"
    )
    # Exactly 20 recorded — proves no lost update under concurrent access.
    assert health_entry["count"] == 20

    get_metrics_registry().reset()


def test_concurrent_predict_rate_limit_enforces_the_exact_limit_under_contention(
    client: TestClient, png_bytes: bytes
) -> None:
    """The P7.4 rate limiter's counter must not lose updates under real
    concurrent load — exactly `max_requests` succeed and the rest are
    rejected, never more than the configured limit (a races-prone counter
    would let extra requests through)."""
    from device_ai.utils.rate_limit import RateLimiter

    limiter = RateLimiter(max_requests=5, window_seconds=60.0)
    _fastapi_app(client).dependency_overrides[dependencies.get_predict_rate_limiter] = (
        lambda: limiter
    )

    status_codes: list[int] = []
    lock = threading.Lock()

    def _call() -> None:
        response = client.post(
            "/predict",
            files=[("images", ("device.png", png_bytes, "image/png"))],
        )
        with lock:
            status_codes.append(response.status_code)

    try:
        threads = [threading.Thread(target=_call) for _ in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
    finally:
        overrides = _fastapi_app(client).dependency_overrides
        del overrides[dependencies.get_predict_rate_limiter]

    assert len(status_codes) == 15
    succeeded = sum(1 for c in status_codes if c != 429)
    rejected = sum(1 for c in status_codes if c == 429)
    assert succeeded == 5, f"expected exactly 5 successes, got {succeeded}"
    assert rejected == 10


# ---------------------------------------------------------------------------
# Fabric RPC timeout (slow-but-reachable peer — distinct from unreachable)
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_gateway_slow(tmp_path: Path):
    """A running fake Fabric Gateway that delays every Evaluate response."""
    server_identity = generate_self_signed_identity("localhost")
    behavior = FakeGatewayBehavior(evaluate_delay_seconds=2.0)
    with FakeFabricGateway(server_identity, behavior, tmp_path) as fake:
        yield fake


def test_evaluate_transaction_times_out_against_a_slow_but_reachable_peer(
    fake_gateway_slow: FakeFabricGateway, tmp_path: Path
) -> None:
    """A peer that accepts the connection but never responds in time raises
    FabricUnavailable via a genuine grpc.StatusCode.DEADLINE_EXCEEDED — not
    merely simulated by closing the port (already covered by
    test_evaluate_transaction_unavailable_when_peer_down in
    test_p62_fabric_gateway.py). The client's own configured
    fabric_timeout_seconds must actually be enforced, not just accepted as
    a settings field."""
    identity = generate_self_signed_identity("client-identity")
    cert_path = tmp_path / "client_cert.pem"
    key_path = tmp_path / "client_key.pem"
    cert_path.write_bytes(identity.cert_pem)
    key_path.write_bytes(identity.key_pem)

    settings = _fabric_settings(
        fake_gateway_slow,
        cert_path,
        key_path,
        # Well below the server's 2s injected delay, well above zero —
        # not a brittle near-equal threshold.
        fabric_timeout_seconds=0.5,
    )
    client_under_test = FabricGatewayClient(settings)

    with pytest.raises(FabricUnavailable):
        client_under_test.evaluate_transaction("GetDeviceAnchor", "DEV-TIMEOUT-01")
