"""CHANGE-009 — Collector Web -> Device AI registration.

Covers the two independent defects found in manual QA:

1. No CORSMiddleware was registered at all, so every cross-origin request
   from a browser (including the OPTIONS preflight) was rejected by the
   browser itself — device_ai returned 405 for OPTIONS (no route handles
   it) and never emitted Access-Control-Allow-Origin on any response.

2. A browser's real FormData.append() silently coerces a plain
   `{ uri, name, type }` object (the React-Native-only upload shape the
   Collector app used unconditionally) to the string "[object Object]"
   instead of raising an error. device_ai's own
   RequestValidationError handler then crashed *while building the 422
   response* — Pydantic v2 puts a raw (non-JSON-serializable) ValueError
   instance in ctx.error for a failed UploadFile check — cascading to the
   generic exception handler and a misleading 500. Fixed independently in
   api/errors.py; covered here end-to-end via the exact malformed body a
   real browser produces.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.configs.settings import Settings, get_settings

_ALLOWED_ORIGINS = [
    "http://localhost:8080",
    "http://localhost:5173",
    "http://10.13.29.243:5173",
    "http://localhost:8081",
    "http://localhost:8082",
]


def _make_test_image_bytes(w: int = 100, h: int = 100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color=(120, 140, 180)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def cors_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="development",
        device_backend="memory",
        device_store_dir=tmp_path / "devices",
        log_level="WARNING",
        cors_origins_raw=",".join(_ALLOWED_ORIGINS),
    )


@pytest.fixture()
def client(cors_settings: Settings) -> TestClient:
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(cors_settings)
    app.dependency_overrides[get_settings] = lambda: cors_settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


# ---------------------------------------------------------------------------
# CORS: allowed origins, disallowed origins, credentials, no wildcard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:8082", "http://localhost:8081", "http://localhost:5173", "http://localhost:8080"],
)
def test_register_preflight_allows_configured_origin(client: TestClient, origin: str) -> None:
    """OPTIONS /devices/register succeeds and grants an allowed origin (was 405, no ACAO)."""
    resp = client.options(
        "/devices/register",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code < 300, resp.text
    assert resp.headers.get("access-control-allow-origin") == origin


def test_register_preflight_rejects_unrelated_origin(client: TestClient) -> None:
    resp = client.options(
        "/devices/register",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.headers.get("access-control-allow-origin") is None


def test_actual_response_never_emits_wildcard_origin(client: TestClient) -> None:
    resp = client.get("/health", headers={"Origin": "http://localhost:8082"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:8082"
    assert resp.headers.get("access-control-allow-origin") != "*"


def test_credentials_header_present_for_allowed_origin(client: TestClient) -> None:
    """Access-Control-Allow-Credentials stays true for an allowed origin (unchanged posture)."""
    resp = client.get("/health", headers={"Origin": "http://localhost:8082"})
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_disallowed_origin_gets_no_cors_headers_on_a_real_request(client: TestClient) -> None:
    """The request still succeeds server-side (device_ai has no origin-based auth) —
    it is the *browser* that must refuse to expose the response without ACAO."""
    resp = client.get("/health", headers={"Origin": "http://evil.example"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") is None


# ---------------------------------------------------------------------------
# The 500 -> 422 fix: exact malformed body a real browser's FormData produces
# ---------------------------------------------------------------------------


def test_browser_shaped_malformed_upload_returns_422_not_500(client: TestClient) -> None:
    """Reproduces deviceAiApi.ts's pre-fix toFormData() output on web: appending a
    plain `{uri,name,type}` object silently becomes this exact text field in a real
    browser's FormData, not a file part."""
    resp = client.post(
        "/devices/register",
        data={"images": "[object Object]"},
        headers={"Origin": "http://localhost:8082"},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "REQUEST_VALIDATION_ERROR"
    # The response itself must still carry CORS headers (it goes through the
    # generic Exception path pre-fix, but even the 422 path must not lose them).
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:8082"


def test_browser_shaped_malformed_upload_details_are_json_safe(client: TestClient) -> None:
    """The 422 body's error.details must be plain JSON — no raw exception objects
    (this is precisely what made the earlier, unfixed response 500 instead)."""
    resp = client.post("/devices/register", data={"images": "[object Object]"})
    assert resp.status_code == 422
    errors = resp.json()["error"]["details"]["errors"]
    assert errors[0]["msg"]
    assert isinstance(errors[0]["ctx"], dict)


# ---------------------------------------------------------------------------
# Existing multipart contract is unaffected by either fix
# ---------------------------------------------------------------------------


def test_genuine_multipart_upload_still_succeeds(client: TestClient) -> None:
    """A real file part (what curl and the RN-native path send) still registers fine."""
    png_data = _make_test_image_bytes()
    resp = client.post(
        "/devices/register",
        files=[("images", ("capture.png", png_data, "image/png"))],
        headers={"Origin": "http://localhost:8082"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:8082"
