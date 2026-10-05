"""Test Suite for P6.2 — Backend Fabric Gateway Integration.

No test in this suite requires a live Fabric network or Docker. Two testing
strategies are used together:

1. Direct unit tests against :class:`FabricGatewayClient` /
   :class:`FabricExternalTrustLedger` with ``FABRIC_ENABLED=false`` or
   deliberately invalid configuration — no network activity at all.
2. Tests against :class:`fabric_test_server.FakeFabricGateway`, an in-process
   TLS gRPC server implementing the real ``gateway.Gateway`` service contract
   (compiled from the vendored, unmodified upstream Fabric protobuf
   definitions in ``blockchain/fabric-protos/``). This validates the client's
   TLS channel construction, identity loading, proposal construction, ECDSA
   signing, and the Endorse/Submit/CommitStatus/Evaluate RPC sequence
   end-to-end against a real (if not Fabric-specific) peer.

What strategy 2 does **not** validate: genuine Fabric-specific behavior only
a real peer performs (MSP/identity membership validation, endorsement policy
satisfaction, real chaincode execution, ledger commit atomicity). See
``reports/P6_2_FABRIC_GATEWAY_INTEGRATION.md`` for the honest scope of what
was and was not verified.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from pathlib import Path

import grpc
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.configs.settings import Settings, get_settings
from device_ai.devices.brand import RuleBasedBrandIntelligence
from device_ai.devices.carbon import EstimatedBurdenCarbonIntelligence
from device_ai.devices.condition import BaselineConditionIntelligence
from device_ai.devices.enrichment_service import DeviceIntelligenceService
from device_ai.devices.external_trust import (
    ExternalTrustAnchor,
    ExternalTrustLedger,
    ExternalTrustStatus,
    FabricExternalTrustLedger,
    InMemoryExternalTrustLedger,
)
from device_ai.devices.fabric_gateway_client import (
    FabricGatewayClient,
    build_fabric_gateway_client,
)
from device_ai.devices.material import ProfileBasedMaterialIntelligence
from device_ai.devices.repository import InMemoryDeviceRepository
from device_ai.devices.service import DeviceRegistrationService
from device_ai.devices.trust_anchor import (
    DevicePassportTrustService,
    InMemoryTrustAnchorRepository,
    TrustAnchorPolicy,
)
from device_ai.exceptions import (
    FabricConfigurationError,
    FabricConnectionError,
    FabricGatewayError,
    FabricNotConfigured,
    FabricQueryError,
    FabricTransactionError,
)
from device_ai.inference.pipeline import build_detection_pipeline
from device_ai.inference.predictor import Detection, DetectionResult, Detector
from device_ai.preprocessing.image_loader import LoadedImage
from device_ai.tests.fabric_test_server import (
    FakeFabricGateway,
    FakeGatewayBehavior,
    generate_self_signed_identity,
)

# ---------------------------------------------------------------------------
# Shared local helpers (mirrors the pattern used by test_p511_external_trust.py)
# ---------------------------------------------------------------------------


def _make_test_image_bytes(w: int = 120, h: int = 120) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color=(90, 110, 140)).save(buf, format="PNG")
    return buf.getvalue()


def _make_loaded_image(name: str = "test.png") -> LoadedImage:
    raw = _make_test_image_bytes()
    pil_img = Image.open(io.BytesIO(raw)).convert("RGB")
    return LoadedImage(filename=name, content_type="image/png", raw=raw, image=pil_img)


class _FakeDetector(Detector):
    version = "p62-fake-1.0.0"

    def __init__(self, detections: list[Detection] | None = None) -> None:
        self._detections = detections or [
            Detection(label="laptop", confidence=0.96, bounding_box=(10, 10, 100, 100))
        ]

    def detect(self, images: list[LoadedImage]) -> DetectionResult:
        top = self._detections[0] if self._detections else None
        return DetectionResult(
            device_type=top.label.title() if top else "Unknown",
            brand="Unknown",
            confidence=top.confidence if top else 0.0,
            detections=self._detections,
        )


@pytest.fixture()
def identity_files(tmp_path: Path) -> tuple[Path, Path]:
    """A fresh, ephemeral self-signed client identity (cert + EC key) on disk."""
    identity = generate_self_signed_identity("client-identity")
    cert_path = tmp_path / "client_cert.pem"
    key_path = tmp_path / "client_key.pem"
    cert_path.write_bytes(identity.cert_pem)
    key_path.write_bytes(identity.key_pem)
    return cert_path, key_path


@pytest.fixture()
def fake_gateway(tmp_path: Path) -> Iterator[FakeFabricGateway]:
    """A running in-process fake Fabric Gateway TLS gRPC server."""
    server_identity = generate_self_signed_identity("localhost")
    behavior = FakeGatewayBehavior()
    with FakeFabricGateway(server_identity, behavior, tmp_path) as fake:
        yield fake


def _fabric_settings(
    fake: FakeFabricGateway,
    cert_path: Path,
    key_path: Path,
    **overrides: object,
) -> Settings:
    base: dict[str, object] = {
        "fabric_enabled": True,
        "fabric_channel_name": "ecotrace-channel",
        "fabric_chaincode_name": "ecotrace-lifecycle",
        "fabric_msp_id": "EcoTraceOrgMSP",
        "fabric_peer_endpoint": fake.address,
        "fabric_gateway_peer_endpoint": fake.address,
        "fabric_tls_cert_path": str(fake.ca_cert_path),
        "fabric_identity_cert_path": str(cert_path),
        "fabric_identity_key_path": str(key_path),
        "fabric_timeout_seconds": 5.0,
        "log_level": "WARNING",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. Configuration
# ---------------------------------------------------------------------------


def test_fabric_disabled_by_default() -> None:
    """FABRIC_ENABLED defaults to False, matching pre-P6.2 behavior."""
    settings = Settings()
    assert settings.fabric_enabled is False
    assert build_fabric_gateway_client(settings) is None


def test_fabric_settings_read_from_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every FABRIC_* variable named in the P6.2 work order is honored."""
    monkeypatch.setenv("FABRIC_ENABLED", "true")
    monkeypatch.setenv("FABRIC_CHANNEL_NAME", "custom-channel")
    monkeypatch.setenv("FABRIC_CHAINCODE_NAME", "custom-chaincode")
    monkeypatch.setenv("FABRIC_MSP_ID", "CustomMSP")
    monkeypatch.setenv("FABRIC_PEER_ENDPOINT", "peer0.example.com:7051")
    monkeypatch.setenv("FABRIC_GATEWAY_PEER_ENDPOINT", "gateway.example.com:7051")
    monkeypatch.setenv("FABRIC_TLS_CERT_PATH", "/tmp/ca.pem")
    monkeypatch.setenv("FABRIC_IDENTITY_CERT_PATH", "/tmp/cert.pem")
    monkeypatch.setenv("FABRIC_IDENTITY_KEY_PATH", "/tmp/key.pem")
    monkeypatch.setenv("FABRIC_CONNECTION_PROFILE", "/tmp/profile.json")
    monkeypatch.setenv("FABRIC_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("FABRIC_TIMEOUT_SECONDS", "42.5")

    settings = Settings(_env_file=None)
    assert settings.fabric_enabled is True
    assert settings.fabric_channel_name == "custom-channel"
    assert settings.fabric_chaincode_name == "custom-chaincode"
    assert settings.fabric_msp_id == "CustomMSP"
    assert settings.fabric_peer_endpoint == "peer0.example.com:7051"
    assert settings.fabric_gateway_peer_endpoint == "gateway.example.com:7051"
    assert settings.fabric_tls_cert_path == "/tmp/ca.pem"
    assert settings.fabric_identity_cert_path == "/tmp/cert.pem"
    assert settings.fabric_identity_key_path == "/tmp/key.pem"
    assert settings.fabric_connection_profile == "/tmp/profile.json"
    assert settings.fabric_discovery_enabled is True
    assert settings.fabric_timeout_seconds == pytest.approx(42.5)


def test_existing_external_trust_settings_unchanged() -> None:
    """P5.11's external_trust_* fields keep their original defaults (additive, not replaced)."""
    settings = Settings()
    assert settings.external_trust_backend == "memory"
    assert settings.external_trust_channel == "ecotrace-channel"
    assert settings.external_trust_chaincode == "ecotrace-lifecycle"


# ---------------------------------------------------------------------------
# 2. Gateway connection
# ---------------------------------------------------------------------------


def test_connect_success_against_fake_peer(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    cert_path, key_path = identity_files
    settings = _fabric_settings(fake_gateway, cert_path, key_path)
    client = FabricGatewayClient(settings)

    client.connect()
    assert client.is_available() is True

    client.disconnect()
    assert client.is_available() is False


def test_connect_raises_not_configured_when_disabled() -> None:
    settings = Settings(fabric_enabled=False)
    client = FabricGatewayClient(settings)
    with pytest.raises(FabricNotConfigured):
        client.connect()


def test_connect_raises_connection_error_when_peer_unreachable(
    identity_files: tuple[Path, Path], tmp_path: Path
) -> None:
    """A closed local port classifies as FabricConnectionError, not a crash."""
    cert_path, key_path = identity_files
    # A CA cert is still required (checked before the network attempt); reuse
    # a throwaway self-signed cert as the "CA" — the handshake will simply
    # never complete because nothing listens on the port.
    fake_ca = tmp_path / "ca.pem"
    fake_ca.write_bytes(generate_self_signed_identity("unused-ca").cert_pem)
    settings = Settings(
        fabric_enabled=True,
        fabric_gateway_peer_endpoint="localhost:1",  # nothing listens here
        fabric_peer_endpoint="localhost:1",
        fabric_tls_cert_path=str(fake_ca),
        fabric_identity_cert_path=str(cert_path),
        fabric_identity_key_path=str(key_path),
        fabric_timeout_seconds=0.5,
        log_level="WARNING",
    )
    client = FabricGatewayClient(settings)
    with pytest.raises(FabricConnectionError):
        client.connect()


def test_connect_idempotent(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    cert_path, key_path = identity_files
    client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))
    client.connect()
    client.connect()  # second call is a no-op, not an error
    assert client.is_available() is True
    client.disconnect()


# ---------------------------------------------------------------------------
# 3. Successful query
# ---------------------------------------------------------------------------


def test_evaluate_transaction_success(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    cert_path, key_path = identity_files
    client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))
    result = client.evaluate_transaction("GetDeviceAnchor", "DEV-NOT-ANCHORED")
    assert result == "null"  # matches the real chaincode's not-found response


# ---------------------------------------------------------------------------
# 4. Successful transaction
# ---------------------------------------------------------------------------


def test_submit_transaction_success_full_flow(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    cert_path, key_path = identity_files
    client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))

    tx_id = client.submit_transaction(
        "AnchorDevicePassport", "DEV-01", "a" * 64, "sha256"
    )

    assert len(tx_id) == 64  # sha256 hex digest
    assert all(c in "0123456789abcdef" for c in tx_id)
    # The server only accepts a Submit whose envelope carries a non-empty
    # signature — a full round trip proves the client actually signed it.
    assert len(fake_gateway.servicer.submitted_envelopes) == 1
    assert fake_gateway.servicer.submitted_envelopes[0].signature != b""
    assert len(fake_gateway.servicer.commit_status_requests) == 1
    assert fake_gateway.servicer.commit_status_requests[0].transaction_id == tx_id
    # The fake chaincode simulation recorded the anchor.
    assert fake_gateway.servicer.anchors["DEV-01"]["passportFingerprint"] == "a" * 64


def test_submit_then_evaluate_round_trip(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    """A GetDeviceAnchor query after an AnchorDevicePassport submit sees the write."""
    cert_path, key_path = identity_files
    client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))

    client.submit_transaction("AnchorDevicePassport", "DEV-RT", "b" * 64, "sha256")
    raw = client.evaluate_transaction("GetDeviceAnchor", "DEV-RT")
    data = json.loads(raw)
    assert data["deviceId"] == "DEV-RT"
    assert data["passportFingerprint"] == "b" * 64


# ---------------------------------------------------------------------------
# 5. Fabric unavailable
# ---------------------------------------------------------------------------


def test_evaluate_transaction_unavailable_when_peer_down(
    identity_files: tuple[Path, Path], tmp_path: Path
) -> None:
    """`evaluate_transaction` lazily connects first; an unreachable peer at that
    point surfaces as FabricConnectionError (both it and FabricUnavailable are
    FabricGatewayError subclasses mapped to 503 — see test_submit_transaction_
    calls_submit_exactly_once_on_rpc_error for the RPC-level UNAVAILABLE path
    on an *already-connected* channel, classified as FabricUnavailable)."""
    cert_path, key_path = identity_files
    fake_ca = tmp_path / "ca.pem"
    fake_ca.write_bytes(generate_self_signed_identity("unused-ca").cert_pem)
    settings = Settings(
        fabric_enabled=True,
        fabric_gateway_peer_endpoint="localhost:1",
        fabric_peer_endpoint="localhost:1",
        fabric_tls_cert_path=str(fake_ca),
        fabric_identity_cert_path=str(cert_path),
        fabric_identity_key_path=str(key_path),
        fabric_timeout_seconds=0.5,
        log_level="WARNING",
    )
    client = FabricGatewayClient(settings)
    with pytest.raises(FabricConnectionError):
        client.evaluate_transaction("GetDeviceAnchor", "DEV-01")


def test_ledger_verify_anchor_unavailable_when_client_none() -> None:
    """FabricExternalTrustLedger(gateway_client=None) — the FABRIC_ENABLED=false path."""
    ledger = FabricExternalTrustLedger(gateway_client=None)
    result = ledger.verify_anchor("DEV-01", "a" * 64)
    assert result.status == ExternalTrustStatus.UNAVAILABLE


# ---------------------------------------------------------------------------
# 6. Invalid configuration
# ---------------------------------------------------------------------------


def test_missing_tls_cert_path_raises_configuration_error(
    identity_files: tuple[Path, Path],
) -> None:
    cert_path, key_path = identity_files
    settings = Settings(
        fabric_enabled=True,
        fabric_tls_cert_path=None,
        fabric_identity_cert_path=str(cert_path),
        fabric_identity_key_path=str(key_path),
    )
    client = FabricGatewayClient(settings)
    with pytest.raises(FabricConfigurationError):
        client.connect()


def test_missing_identity_paths_raises_configuration_error(tmp_path: Path) -> None:
    ca = tmp_path / "ca.pem"
    ca.write_bytes(generate_self_signed_identity("ca").cert_pem)
    settings = Settings(fabric_enabled=True, fabric_tls_cert_path=str(ca))
    client = FabricGatewayClient(settings)
    with pytest.raises(FabricConfigurationError):
        client.connect()


def test_nonexistent_cert_file_raises_configuration_error(tmp_path: Path) -> None:
    settings = Settings(
        fabric_enabled=True,
        fabric_tls_cert_path=str(tmp_path / "does-not-exist.pem"),
        fabric_identity_cert_path=str(tmp_path / "also-missing.pem"),
        fabric_identity_key_path=str(tmp_path / "also-missing.key"),
    )
    client = FabricGatewayClient(settings)
    with pytest.raises(FabricConfigurationError):
        client.connect()


# ---------------------------------------------------------------------------
# 7. TLS / certificate loading errors
# ---------------------------------------------------------------------------


def test_malformed_pem_cert_raises_configuration_error(tmp_path: Path) -> None:
    identity = generate_self_signed_identity("x")
    bad_cert = tmp_path / "bad_cert.pem"
    bad_cert.write_bytes(b"not a real certificate")
    key_path = tmp_path / "key.pem"
    key_path.write_bytes(identity.key_pem)
    ca = tmp_path / "ca.pem"
    ca.write_bytes(identity.cert_pem)

    settings = Settings(
        fabric_enabled=True,
        fabric_tls_cert_path=str(ca),
        fabric_identity_cert_path=str(bad_cert),
        fabric_identity_key_path=str(key_path),
    )
    client = FabricGatewayClient(settings)
    with pytest.raises(FabricConfigurationError):
        client.connect()


def test_malformed_pem_key_raises_configuration_error(tmp_path: Path) -> None:
    identity = generate_self_signed_identity("x")
    cert_path = tmp_path / "cert.pem"
    cert_path.write_bytes(identity.cert_pem)
    bad_key = tmp_path / "bad_key.pem"
    bad_key.write_bytes(b"not a real private key")
    ca = tmp_path / "ca.pem"
    ca.write_bytes(identity.cert_pem)

    settings = Settings(
        fabric_enabled=True,
        fabric_tls_cert_path=str(ca),
        fabric_identity_cert_path=str(cert_path),
        fabric_identity_key_path=str(bad_key),
    )
    client = FabricGatewayClient(settings)
    with pytest.raises(FabricConfigurationError):
        client.connect()


def test_non_ec_key_rejected(tmp_path: Path) -> None:
    """Fabric MSP identities are ECDSA; an RSA key is rejected with a clear error."""
    from cryptography.hazmat.primitives import serialization as ser
    from cryptography.hazmat.primitives.asymmetric import rsa

    identity = generate_self_signed_identity("x")
    cert_path = tmp_path / "cert.pem"
    cert_path.write_bytes(identity.cert_pem)
    ca = tmp_path / "ca.pem"
    ca.write_bytes(identity.cert_pem)

    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_key_path = tmp_path / "rsa_key.pem"
    rsa_key_path.write_bytes(
        rsa_key.private_bytes(
            encoding=ser.Encoding.PEM,
            format=ser.PrivateFormat.PKCS8,
            encryption_algorithm=ser.NoEncryption(),
        )
    )

    settings = Settings(
        fabric_enabled=True,
        fabric_tls_cert_path=str(ca),
        fabric_identity_cert_path=str(cert_path),
        fabric_identity_key_path=str(rsa_key_path),
    )
    client = FabricGatewayClient(settings)
    with pytest.raises(FabricConfigurationError, match="elliptic-curve"):
        client.connect()


# ---------------------------------------------------------------------------
# 8. Transaction failure
# ---------------------------------------------------------------------------


def test_submit_transaction_non_valid_commit_code_raises(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    from peer import transaction_pb2

    fake_gateway.behavior.commit_result = (
        transaction_pb2.TxValidationCode.MVCC_READ_CONFLICT
    )
    cert_path, key_path = identity_files
    client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))
    with pytest.raises(FabricTransactionError, match="MVCC_READ_CONFLICT"):
        client.submit_transaction("AnchorDevicePassport", "DEV-01", "a" * 64, "sha256")


def test_submit_transaction_endorse_rpc_error_raises(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    fake_gateway.behavior.endorse_error = grpc.StatusCode.PERMISSION_DENIED
    cert_path, key_path = identity_files
    client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))
    with pytest.raises(FabricTransactionError):
        client.submit_transaction("AnchorDevicePassport", "DEV-01", "a" * 64, "sha256")


def test_submit_transaction_submit_rpc_error_raises(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    fake_gateway.behavior.submit_error = grpc.StatusCode.INTERNAL
    cert_path, key_path = identity_files
    client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))
    with pytest.raises(FabricTransactionError):
        client.submit_transaction("AnchorDevicePassport", "DEV-01", "a" * 64, "sha256")


# ---------------------------------------------------------------------------
# 9. Query failure
# ---------------------------------------------------------------------------


def test_evaluate_transaction_rpc_error_raises_query_error(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    fake_gateway.behavior.evaluate_error = grpc.StatusCode.INTERNAL
    cert_path, key_path = identity_files
    client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))
    with pytest.raises(FabricQueryError):
        client.evaluate_transaction("GetDeviceAnchor", "DEV-01")


# ---------------------------------------------------------------------------
# 10. Health check
# ---------------------------------------------------------------------------


def test_health_check_disabled() -> None:
    client = FabricGatewayClient(Settings(fabric_enabled=False))
    result = client.health_check()
    assert result.status == "disabled"


def test_health_check_configuration_error() -> None:
    client = FabricGatewayClient(
        Settings(fabric_enabled=True, fabric_tls_cert_path=None)
    )
    result = client.health_check()
    assert result.status == "configuration_error"


def test_health_check_connected(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    cert_path, key_path = identity_files
    client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))
    result = client.health_check()
    assert result.status == "connected"
    assert result.latency_ms is not None and result.latency_ms >= 0


def test_health_check_unavailable(
    identity_files: tuple[Path, Path], tmp_path: Path
) -> None:
    cert_path, key_path = identity_files
    fake_ca = tmp_path / "ca.pem"
    fake_ca.write_bytes(generate_self_signed_identity("unused-ca").cert_pem)
    settings = Settings(
        fabric_enabled=True,
        fabric_gateway_peer_endpoint="localhost:1",
        fabric_peer_endpoint="localhost:1",
        fabric_tls_cert_path=str(fake_ca),
        fabric_identity_cert_path=str(cert_path),
        fabric_identity_key_path=str(key_path),
        fabric_timeout_seconds=0.5,
    )
    client = FabricGatewayClient(settings)
    result = client.health_check()
    assert result.status == "unavailable"


def test_blockchain_health_endpoint_disabled() -> None:
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    settings = Settings(log_level="WARNING")
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        resp = client.get("/system/blockchain/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["health"]["status"] == "disabled"
    assert body["health"]["fabric_enabled"] is False
    dependencies.reset_dependency_caches()


def test_blockchain_health_endpoint_connected(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    cert_path, key_path = identity_files
    settings = _fabric_settings(fake_gateway, cert_path, key_path)
    gw_client = FabricGatewayClient(settings)

    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings
    # get_fabric_gateway_client() is a plain @lru_cache singleton that calls
    # get_settings() directly (not through FastAPI's DI graph, matching the
    # existing get_external_trust_ledger() pattern) — app.dependency_overrides
    # only intercepts Depends()-declared resolution, so the settings override
    # above does not reach it. Override the singleton itself directly, exactly
    # as the pre-existing P5.11 tests override get_trust_service rather than
    # relying on get_settings alone to reach internal singletons.
    app.dependency_overrides[dependencies.get_fabric_gateway_client] = lambda: gw_client
    with TestClient(app) as client:
        resp = client.get("/system/blockchain/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["health"]["status"] == "connected"
    assert body["health"]["channel"] == "ecotrace-channel"
    assert body["health"]["chaincode"] == "ecotrace-lifecycle"
    dependencies.reset_dependency_caches()


# ---------------------------------------------------------------------------
# 11. ExternalTrustLedger protocol compliance
# ---------------------------------------------------------------------------


def test_fabric_external_trust_ledger_satisfies_protocol() -> None:
    ledger = FabricExternalTrustLedger(gateway_client=None)
    assert isinstance(ledger, ExternalTrustLedger)


def test_fabric_gateway_client_duck_types_the_p511_adapter_contract(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    """A FabricGatewayClient can be injected as FabricExternalTrustLedger's
    gateway_client unmodified — this is the P6.2 integration point."""
    cert_path, key_path = identity_files
    client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))
    ledger = FabricExternalTrustLedger(
        channel="ecotrace-channel",
        chaincode="ecotrace-lifecycle",
        gateway_client=client,
    )
    assert ledger.is_available() is True

    anchor = ExternalTrustAnchor(
        external_anchor_id="ext-1", device_id="DEV-PROTO", passport_fingerprint="c" * 64
    )
    saved = ledger.anchor(anchor)
    assert len(saved.transaction_id) == 64

    fetched = ledger.get_anchor("DEV-PROTO")
    assert fetched is not None
    assert fetched.passport_fingerprint == "c" * 64

    verify = ledger.verify_anchor("DEV-PROTO", "c" * 64)
    assert verify.status == ExternalTrustStatus.VERIFIED

    mismatch = ledger.verify_anchor("DEV-PROTO", "d" * 64)
    assert mismatch.status == ExternalTrustStatus.MISMATCH

    not_found = ledger.verify_anchor("DEV-NEVER-ANCHORED", "e" * 64)
    assert not_found.status == ExternalTrustStatus.NOT_ANCHORED


# ---------------------------------------------------------------------------
# 12. Existing P5 trust behavior (regression)
# ---------------------------------------------------------------------------


def test_p511_offline_behavior_still_exact() -> None:
    """Re-assert the exact P5.11 contract test_fabric_adapter_offline_behavior locks in."""
    from device_ai.exceptions import ExternalLedgerUnavailableError

    fabric_ledger = FabricExternalTrustLedger(
        channel="ecotrace-channel", chaincode="ecotrace-lifecycle", gateway_client=None
    )
    assert fabric_ledger.is_available() is False
    res = fabric_ledger.verify_anchor("DEV-01", "some-hash")
    assert res.status == ExternalTrustStatus.UNAVAILABLE
    with pytest.raises(ExternalLedgerUnavailableError):
        fabric_ledger.anchor(
            ExternalTrustAnchor(
                external_anchor_id="e1", device_id="DEV-01", passport_fingerprint="abc"
            )
        )


def test_default_settings_still_use_memory_ledger() -> None:
    """P6.2 is purely additive: default settings behave exactly as before."""
    settings = Settings()
    ledger = dependencies.build_external_trust_ledger(settings)
    assert isinstance(ledger, InMemoryExternalTrustLedger)


# ---------------------------------------------------------------------------
# 13. Existing API compatibility
# ---------------------------------------------------------------------------


def test_existing_trust_endpoints_unaffected_with_fabric_disabled() -> None:
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    settings = Settings(log_level="WARNING")
    dev_repo = InMemoryDeviceRepository()
    local_repo = InMemoryTrustAnchorRepository()
    ext_ledger = InMemoryExternalTrustLedger()

    pipeline = build_detection_pipeline(
        detector=_FakeDetector(
            [Detection(label="laptop", confidence=0.95, bounding_box=(5, 5, 90, 90))]
        ),
        model_version="1.0.0",
        year=2026,
    )
    reg_service = DeviceRegistrationService(
        repository=dev_repo, pipeline=pipeline, settings=settings
    )
    trust_service = DevicePassportTrustService(
        device_service=reg_service,
        anchor_repository=local_repo,
        policy=TrustAnchorPolicy.STRICT,
        settings=settings,
        external_ledger=ext_ledger,
    )

    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline
    app.dependency_overrides[dependencies.get_device_service] = lambda: reg_service
    app.dependency_overrides[dependencies.get_trust_service] = lambda: trust_service

    with TestClient(app) as client:
        reg_resp = client.post(
            "/devices/register",
            data={"capture_id": "cap-p62-compat"},
            files=[("images", ("laptop.png", _make_test_image_bytes(), "image/png"))],
        )
        assert reg_resp.status_code == 200
        device_id = reg_resp.json()["devices"][0]["device_id"]

        v_pre = client.get(f"/devices/{device_id}/passport/external-anchor/verify")
        assert v_pre.status_code == 200
        assert v_pre.json()["verification"]["status"] == "NOT_ANCHORED"

        full = client.get(f"/devices/{device_id}/trust/full")
        assert full.status_code == 200
        assert full.json()["trust"]["external_status"] == "NOT_ANCHORED"

    dependencies.reset_dependency_caches()


# ---------------------------------------------------------------------------
# 14. Read-only verification invariants
# ---------------------------------------------------------------------------


def test_health_check_never_calls_submit_or_endorse(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    cert_path, key_path = identity_files
    client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))
    client.health_check()
    client.health_check()
    assert fake_gateway.servicer.submitted_envelopes == []
    assert fake_gateway.servicer.commit_status_requests == []
    assert fake_gateway.servicer.anchors == {}


def test_evaluate_transaction_never_calls_submit(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    cert_path, key_path = identity_files
    client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))
    client.evaluate_transaction("GetDeviceAnchor", "DEV-01")
    assert fake_gateway.servicer.submitted_envelopes == []
    assert fake_gateway.servicer.anchors == {}


def test_verify_device_passport_external_is_read_only(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    """DevicePassportTrustService.verify_device_passport_external performs zero writes."""
    cert_path, key_path = identity_files
    gw_client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))
    ext_ledger = FabricExternalTrustLedger(gateway_client=gw_client)

    settings = Settings(log_level="WARNING")
    dev_repo = InMemoryDeviceRepository()
    pipeline = build_detection_pipeline(
        detector=_FakeDetector(), model_version="1.0.0", year=2026
    )
    reg_service = DeviceRegistrationService(
        repository=dev_repo, pipeline=pipeline, settings=settings
    )
    trust_service = DevicePassportTrustService(
        device_service=reg_service,
        anchor_repository=InMemoryTrustAnchorRepository(),
        policy=TrustAnchorPolicy.STRICT,
        settings=settings,
        external_ledger=ext_ledger,
    )

    records, _ = reg_service.register_from_images(
        [_make_loaded_image()], capture_id="cap-p62-readonly"
    )
    device_id = records[0].device_id

    trust_service.verify_device_passport_external(device_id)
    trust_service.verify_device_passport_external(device_id)

    assert fake_gateway.servicer.submitted_envelopes == []
    assert fake_gateway.servicer.anchors == {}
    assert dev_repo.get(device_id) is not None  # device record itself untouched


# ---------------------------------------------------------------------------
# 15. No secret leakage in errors/logs
# ---------------------------------------------------------------------------


def test_configuration_error_never_contains_key_bytes(tmp_path: Path) -> None:
    identity = generate_self_signed_identity("x")
    marker = b"-----BEGIN PRIVATE KEY SECRET MARKER-----"
    bad_key = tmp_path / "bad_key.pem"
    bad_key.write_bytes(marker + b"\nnot actually valid pem content")
    cert_path = tmp_path / "cert.pem"
    cert_path.write_bytes(identity.cert_pem)
    ca = tmp_path / "ca.pem"
    ca.write_bytes(identity.cert_pem)

    settings = Settings(
        fabric_enabled=True,
        fabric_tls_cert_path=str(ca),
        fabric_identity_cert_path=str(cert_path),
        fabric_identity_key_path=str(bad_key),
    )
    client = FabricGatewayClient(settings)
    with pytest.raises(FabricConfigurationError) as exc_info:
        client.connect()

    rendered = f"{exc_info.value.message} {exc_info.value.details}"
    assert b"SECRET MARKER".decode() not in rendered
    assert "BEGIN PRIVATE KEY" not in rendered
    # Only the path, never the file content, should appear in details.
    assert exc_info.value.details.get("path") == str(bad_key)


def test_connection_error_message_has_no_pem_content(
    identity_files: tuple[Path, Path], tmp_path: Path
) -> None:
    cert_path, key_path = identity_files
    fake_ca = tmp_path / "ca.pem"
    ca_identity = generate_self_signed_identity("unused-ca")
    fake_ca.write_bytes(ca_identity.cert_pem)
    settings = Settings(
        fabric_enabled=True,
        fabric_gateway_peer_endpoint="localhost:1",
        fabric_peer_endpoint="localhost:1",
        fabric_tls_cert_path=str(fake_ca),
        fabric_identity_cert_path=str(cert_path),
        fabric_identity_key_path=str(key_path),
        fabric_timeout_seconds=0.5,
    )
    client = FabricGatewayClient(settings)
    with pytest.raises(FabricConnectionError) as exc_info:
        client.connect()
    rendered = f"{exc_info.value.message} {exc_info.value.details}"
    assert "BEGIN CERTIFICATE" not in rendered
    assert "BEGIN PRIVATE KEY" not in rendered
    assert ca_identity.key_pem.decode() not in rendered


# ---------------------------------------------------------------------------
# 16. No duplicate transaction retry
# ---------------------------------------------------------------------------


def test_submit_transaction_calls_submit_exactly_once_on_failure(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    """A commit failure must not trigger an automatic re-submit (would risk a duplicate write)."""
    from peer import transaction_pb2

    fake_gateway.behavior.commit_result = (
        transaction_pb2.TxValidationCode.ENDORSEMENT_POLICY_FAILURE
    )
    cert_path, key_path = identity_files
    client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))

    with pytest.raises(FabricTransactionError):
        client.submit_transaction("AnchorDevicePassport", "DEV-01", "a" * 64, "sha256")

    assert (
        len(fake_gateway.servicer.submitted_envelopes) == 1
    )  # exactly one Submit, no retry


def test_submit_transaction_calls_submit_exactly_once_on_rpc_error(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    call_count = {"n": 0}

    def count_submit(_request: object) -> None:
        call_count["n"] += 1

    fake_gateway.behavior.on_submit = count_submit
    fake_gateway.behavior.commit_error = grpc.StatusCode.UNAVAILABLE
    cert_path, key_path = identity_files
    client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))

    with pytest.raises(FabricGatewayError):
        client.submit_transaction("AnchorDevicePassport", "DEV-01", "a" * 64, "sha256")

    assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# 17. Disabled Fabric mode (end-to-end)
# ---------------------------------------------------------------------------


def test_disabled_mode_end_to_end_via_dependency_wiring() -> None:
    settings = Settings(
        external_trust_backend="fabric", fabric_enabled=False, log_level="WARNING"
    )
    ledger = dependencies.build_external_trust_ledger(settings)
    assert isinstance(ledger, FabricExternalTrustLedger)
    assert ledger.is_available() is False
    result = ledger.verify_anchor("DEV-01", "a" * 64)
    assert result.status == ExternalTrustStatus.UNAVAILABLE


# ---------------------------------------------------------------------------
# 18 & 19. Full trust evaluation — Fabric available vs. unavailable
# ---------------------------------------------------------------------------


def _build_full_trust_environment(
    ext_ledger: ExternalTrustLedger,
) -> tuple[
    DevicePassportTrustService,
    DeviceRegistrationService,
    DeviceIntelligenceService,
    InMemoryDeviceRepository,
]:
    settings = Settings(log_level="WARNING")
    dev_repo = InMemoryDeviceRepository()
    pipeline = build_detection_pipeline(
        detector=_FakeDetector(
            [Detection(label="monitor", confidence=0.95, bounding_box=(5, 5, 90, 90))]
        ),
        model_version="1.0.0",
        year=2026,
    )
    reg_service = DeviceRegistrationService(
        repository=dev_repo, pipeline=pipeline, settings=settings
    )
    enrich_service = DeviceIntelligenceService(
        repository=dev_repo,
        brand_intelligence=RuleBasedBrandIntelligence(),
        condition_intelligence=BaselineConditionIntelligence(),
        material_intelligence=ProfileBasedMaterialIntelligence(),
        carbon_intelligence=EstimatedBurdenCarbonIntelligence(),
        settings=settings,
    )
    trust_service = DevicePassportTrustService(
        device_service=reg_service,
        anchor_repository=InMemoryTrustAnchorRepository(),
        policy=TrustAnchorPolicy.STRICT,
        settings=settings,
        external_ledger=ext_ledger,
    )
    return trust_service, reg_service, enrich_service, dev_repo


def test_full_trust_status_with_fabric_available(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    cert_path, key_path = identity_files
    gw_client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))
    ext_ledger = FabricExternalTrustLedger(gateway_client=gw_client)
    trust_service, reg_service, enrich_service, _ = _build_full_trust_environment(
        ext_ledger
    )

    records, _ = reg_service.register_from_images(
        [_make_loaded_image()], capture_id="cap-p62-full-available"
    )
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell UltraSharp")
    trust_service.anchor_device_passport(device_id)

    anchor, is_new = trust_service.anchor_device_passport_externally(device_id)
    assert is_new is True
    assert len(anchor.transaction_id) == 64

    full = trust_service.get_full_device_trust_status(device_id)
    assert full.external_status == "VERIFIED"
    assert full.overall_status == "VERIFIED"


def test_full_trust_status_with_fabric_unavailable(
    identity_files: tuple[Path, Path], tmp_path: Path
) -> None:
    cert_path, key_path = identity_files
    fake_ca = tmp_path / "ca.pem"
    fake_ca.write_bytes(generate_self_signed_identity("unused-ca").cert_pem)
    settings = Settings(
        fabric_enabled=True,
        fabric_gateway_peer_endpoint="localhost:1",
        fabric_peer_endpoint="localhost:1",
        fabric_tls_cert_path=str(fake_ca),
        fabric_identity_cert_path=str(cert_path),
        fabric_identity_key_path=str(key_path),
        fabric_timeout_seconds=0.5,
    )
    gw_client = FabricGatewayClient(settings)
    ext_ledger = FabricExternalTrustLedger(gateway_client=gw_client)
    trust_service, reg_service, enrich_service, _ = _build_full_trust_environment(
        ext_ledger
    )

    records, _ = reg_service.register_from_images(
        [_make_loaded_image()], capture_id="cap-p62-full-unavailable"
    )
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell UltraSharp")
    trust_service.anchor_device_passport(device_id)

    # verify_device_passport_external must not raise even though Fabric is
    # unreachable — it reports UNAVAILABLE, and local VERIFIED still carries
    # the overall status per compute_overall_trust_status's precedence.
    full = trust_service.get_full_device_trust_status(device_id)
    assert full.external_status == "UNAVAILABLE"
    assert full.local_status == "VERIFIED"
    assert full.overall_status == "VERIFIED"


# ---------------------------------------------------------------------------
# 20. Observability — Fabric transaction metrics (P7.3)
# ---------------------------------------------------------------------------


def test_submit_transaction_alias_records_a_successful_metric(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    """``submitTransaction`` — the real call surface used by
    ``FabricExternalTrustLedger`` — records a succeeded transaction, proving
    the P7.3 metrics hook observes genuine traffic through the same real
    fake-server round trip P6.2's own tests use, not a mock of the client
    itself."""
    from device_ai.utils.metrics import get_metrics_registry

    get_metrics_registry().reset()
    cert_path, key_path = identity_files
    client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))

    tx_id = client.submitTransaction(
        "AnchorDevicePassport", "DEV-M1", "c" * 64, "sha256"
    )

    assert len(tx_id) == 64
    snapshot = get_metrics_registry().snapshot()
    assert snapshot["fabric"] == {"transactions": 1, "succeeded": 1, "failed": 0}


def test_evaluate_transaction_alias_records_a_successful_metric(
    fake_gateway: FakeFabricGateway, identity_files: tuple[Path, Path]
) -> None:
    from device_ai.utils.metrics import get_metrics_registry

    get_metrics_registry().reset()
    cert_path, key_path = identity_files
    client = FabricGatewayClient(_fabric_settings(fake_gateway, cert_path, key_path))

    client.evaluateTransaction("GetDeviceAnchor", "DEV-NOT-ANCHORED")

    snapshot = get_metrics_registry().snapshot()
    assert snapshot["fabric"] == {"transactions": 1, "succeeded": 1, "failed": 0}


def test_submit_transaction_alias_records_a_failed_metric_and_still_raises(
    identity_files: tuple[Path, Path], tmp_path: Path
) -> None:
    """A connection failure is recorded as ``failed``, and the original
    exception still propagates unchanged — the metrics hook must never
    swallow an error."""
    from device_ai.utils.metrics import get_metrics_registry

    get_metrics_registry().reset()
    cert_path, key_path = identity_files
    fake_ca = tmp_path / "ca.pem"
    fake_ca.write_bytes(generate_self_signed_identity("unused-ca").cert_pem)
    settings = Settings(
        fabric_enabled=True,
        fabric_gateway_peer_endpoint="localhost:1",
        fabric_peer_endpoint="localhost:1",
        fabric_tls_cert_path=str(fake_ca),
        fabric_identity_cert_path=str(cert_path),
        fabric_identity_key_path=str(key_path),
        fabric_timeout_seconds=0.5,
        log_level="WARNING",
    )
    client = FabricGatewayClient(settings)

    with pytest.raises(FabricConnectionError):
        client.submitTransaction("AnchorDevicePassport", "DEV-FAIL", "d" * 64, "sha256")

    snapshot = get_metrics_registry().snapshot()
    assert snapshot["fabric"] == {"transactions": 1, "succeeded": 0, "failed": 1}
