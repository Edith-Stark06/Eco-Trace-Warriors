"""Hyperledger Fabric Gateway client (P6.2).

A real gRPC client for the Fabric Gateway service (``Endorse`` / ``Submit`` /
``CommitStatus`` / ``Evaluate``), built directly against the vendored,
unmodified protobuf definitions under ``blockchain/fabric-protos/``.

Why a hand-built gRPC client: Hyperledger Fabric does not publish an official
Python SDK for the Gateway service — only Go, Node.js and Java (verified via
web search during P6.2 reconnaissance; see
``reports/P6_2_FABRIC_GATEWAY_INTEGRATION.md``). The Gateway is a plain gRPC
service, so every unsupported-language client talks to it the same way this
one does: compile the official ``.proto`` contract and speak the protocol
directly. ``grpcio`` is the standard, justified dependency for that.

Honesty contract:

* ``FABRIC_ENABLED=false`` (the default) — every method fails fast with
  :class:`~device_ai.exceptions.FabricNotConfigured`. Zero network activity,
  identical to the pre-P6.2 behavior of an unconfigured
  :class:`~device_ai.devices.external_trust.FabricExternalTrustLedger`.
* ``FABRIC_ENABLED=true`` but no live peer reachable — :meth:`is_available`
  and :meth:`health_check` honestly report the peer unreachable;
  :meth:`evaluate_transaction` / :meth:`submit_transaction` raise
  :class:`~device_ai.exceptions.FabricUnavailable`. Nothing here ever
  fabricates a successful anchor or verification result.
* This client has been built against the authentic Fabric Gateway wire
  protocol (message shapes compiled from unmodified, verbatim upstream
  ``.proto`` sources) but has **not** been exercised against a live Fabric
  peer/orderer, because none exists in this repository or execution
  environment. Treat end-to-end wire correctness (proposal/endorsement/commit
  round-tripping against a real peer) as unverified pending an integration
  test against a real Fabric dev network — see the P6.2 report's "Fabric
  live-network status" section.

Determinism / security notes:

* Timestamps for chaincode-level auditing come from the chaincode itself
  (the P6.1 contract stamps every mutation from ``ctx.stub.getTxTimestamp``);
  this client only supplies the outer ``ChannelHeader.timestamp`` Fabric's
  ordering/validation machinery requires, using the wall clock at proposal
  time (standard Fabric client behavior — every SDK does this).
* Never logs certificate or private key contents — only file paths and
  parse/connect success or failure.
* :meth:`submit_transaction` never retries: a write is endorsed and
  submitted at most once per call. Retrying a submit that may have already
  reached the orderer risks a duplicate on-chain transaction. Callers that
  want a retry policy must decide it above this layer (P6.2 does not add
  one — see the report's "Retry / resilience" section).
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)
from google.protobuf.timestamp_pb2 import Timestamp
from loguru import logger

from ..configs.settings import Settings
from ..exceptions import (
    FabricConfigurationError,
    FabricConnectionError,
    FabricNotConfigured,
    FabricQueryError,
    FabricTransactionError,
    FabricUnavailable,
)
from ..utils.metrics import get_metrics_registry

# The compiled stubs under `devices/fabric_pb/` use bare top-level imports
# (`from gateway import gateway_pb2`, `from common import common_pb2`, ...)
# because that is how `protoc`/`grpc_tools` generates them relative to the
# `-I` root, not relative to this package. Prepending that directory to
# `sys.path` once (idempotent) makes them importable without hand-editing
# generated code. See `blockchain/fabric-protos/README.md` for provenance
# and how to regenerate.
_PB_ROOT = str(Path(__file__).resolve().parent / "fabric_pb")
if _PB_ROOT not in sys.path:
    sys.path.insert(0, _PB_ROOT)

import grpc  # noqa: E402 - after sys.path bootstrap above
from common import common_pb2  # noqa: E402
from gateway import gateway_pb2, gateway_pb2_grpc  # noqa: E402
from msp import identities_pb2  # noqa: E402
from peer import (  # noqa: E402
    chaincode_pb2,
    proposal_pb2,
    transaction_pb2,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class FabricConnectionState(str, Enum):
    """Lifecycle state of the Gateway client's gRPC connection."""

    DISABLED = "disabled"
    UNCONFIGURED = "unconfigured"
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class FabricHealthStatus:
    """Result of a Fabric Gateway health evaluation.

    ``status`` distinguishes the five states P6.2 requires:
    ``disabled`` / ``unavailable`` / ``connected`` / ``healthy`` /
    ``configuration_error``.
    """

    status: str
    channel: str
    chaincode: str
    msp_id: str
    peer_endpoint: str
    message: str
    checked_at: str = field(default_factory=lambda: _utc_now().isoformat())
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        return {
            "status": self.status,
            "channel": self.channel,
            "chaincode": self.chaincode,
            "msp_id": self.msp_id,
            "peer_endpoint": self.peer_endpoint,
            "message": self.message,
            "checked_at": self.checked_at,
            "latency_ms": self.latency_ms,
        }


class FabricGatewayClient:
    """Direct gRPC client for the Hyperledger Fabric Gateway service.

    Duck-types the pre-existing ``gateway_client`` contract that
    :class:`~device_ai.devices.external_trust.FabricExternalTrustLedger`
    already expects (``submitTransaction(name, *args) -> tx_id``,
    ``evaluateTransaction(name, *args) -> payload_str``), via
    :meth:`submitTransaction` / :meth:`evaluateTransaction`, so it can be
    injected as that adapter's ``gateway_client`` with zero changes to
    ``external_trust.py``'s calling convention (locked in by the P5.11 test
    ``test_fabric_live_client_adapter_invocations``). Its own primary API
    (:meth:`connect`, :meth:`disconnect`, :meth:`submit_transaction`,
    :meth:`evaluate_transaction`, :meth:`health_check`,
    :meth:`is_available`) is the snake_case surface the P6.2 work order
    specifies.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._channel: grpc.Channel | None = None
        self._stub: gateway_pb2_grpc.GatewayStub | None = None
        self._identity_cert: x509.Certificate | None = None
        self._identity_key: ec.EllipticCurvePrivateKey | None = None
        self._creator_bytes: bytes | None = None
        self._state: FabricConnectionState = (
            FabricConnectionState.DISABLED
            if not settings.fabric_enabled
            else FabricConnectionState.UNCONFIGURED
        )

    # -----------------------------------------------------------------
    # Connection lifecycle
    # -----------------------------------------------------------------

    def connect(self) -> None:
        """Establish the Fabric Gateway gRPC connection.

        Loads the configured TLS/identity material, opens a TLS gRPC channel
        to ``fabric_gateway_peer_endpoint``, and waits (up to
        ``fabric_timeout_seconds``) for the channel to become ready.
        Idempotent: a second call while already connected is a no-op.

        Raises:
            FabricNotConfigured: ``FABRIC_ENABLED`` is False.
            FabricConfigurationError: A configured cert/key path is missing
                or unparseable.
            FabricConnectionError: The channel could not reach the peer
                within the configured timeout.
        """
        if not self._settings.fabric_enabled:
            self._state = FabricConnectionState.DISABLED
            raise FabricNotConfigured(
                "Fabric Gateway is disabled (FABRIC_ENABLED=false).",
                details={"channel": self._settings.fabric_channel_name},
            )

        if self._state == FabricConnectionState.CONNECTED and self._channel is not None:
            return

        credentials = self._build_channel_credentials()
        self._load_identity()

        target = self._settings.fabric_gateway_peer_endpoint
        options = (
            (("grpc.ssl_target_name_override", self._peer_host()),)
            if self._peer_host()
            else ()
        )
        channel = grpc.secure_channel(target, credentials, options=options)

        try:
            grpc.channel_ready_future(channel).result(
                timeout=self._settings.fabric_timeout_seconds
            )
        except grpc.FutureTimeoutError as exc:
            channel.close()
            self._state = FabricConnectionState.ERROR
            raise FabricConnectionError(
                f"Fabric Gateway peer at '{target}' did not become ready within "
                f"{self._settings.fabric_timeout_seconds}s.",
                details={
                    "peer_endpoint": target,
                    "channel": self._settings.fabric_channel_name,
                },
            ) from exc

        self._channel = channel
        self._stub = gateway_pb2_grpc.GatewayStub(channel)
        self._state = FabricConnectionState.CONNECTED
        logger.bind(
            channel=self._settings.fabric_channel_name,
            chaincode=self._settings.fabric_chaincode_name,
            peer_endpoint=target,
        ).info("Fabric Gateway gRPC channel connected.")

    def disconnect(self) -> None:
        """Close the Fabric Gateway gRPC connection, if open."""
        if self._channel is not None:
            self._channel.close()
        self._channel = None
        self._stub = None
        self._state = (
            FabricConnectionState.DISABLED
            if not self._settings.fabric_enabled
            else FabricConnectionState.DISCONNECTED
        )
        logger.bind(channel=self._settings.fabric_channel_name).info(
            "Fabric Gateway gRPC channel disconnected."
        )

    def is_available(self) -> bool:
        """Return True only if the client is actually connected to a live peer.

        Cheap and read-only: reports the cached connection state rather than
        opening a new connection. Callers that need a fresh check should use
        :meth:`health_check`.
        """
        return (
            self._state == FabricConnectionState.CONNECTED and self._channel is not None
        )

    def health_check(self) -> FabricHealthStatus:
        """Evaluate Fabric Gateway health without submitting any transaction.

        Strictly connection-level: a fresh TLS handshake / channel-ready
        probe against the configured peer, never a chaincode ``Evaluate`` or
        ``Submit`` call, and never any database write or audit event.

        Returns:
            A :class:`FabricHealthStatus` with one of ``disabled``,
            ``configuration_error``, ``unavailable``, ``connected``.
        """
        channel_name = self._settings.fabric_channel_name
        chaincode_name = self._settings.fabric_chaincode_name
        msp_id = self._settings.fabric_msp_id
        peer_endpoint = self._settings.fabric_gateway_peer_endpoint

        if not self._settings.fabric_enabled:
            return FabricHealthStatus(
                status="disabled",
                channel=channel_name,
                chaincode=chaincode_name,
                msp_id=msp_id,
                peer_endpoint=peer_endpoint,
                message=(
                    "Fabric Gateway integration is disabled (FABRIC_ENABLED=false)."
                ),
            )

        try:
            credentials = self._build_channel_credentials()
            self._load_identity()
        except FabricConfigurationError as exc:
            return FabricHealthStatus(
                status="configuration_error",
                channel=channel_name,
                chaincode=chaincode_name,
                msp_id=msp_id,
                peer_endpoint=peer_endpoint,
                message=exc.message,
            )

        start = time.perf_counter()
        options = (
            (("grpc.ssl_target_name_override", self._peer_host()),)
            if self._peer_host()
            else ()
        )
        probe_channel = grpc.secure_channel(peer_endpoint, credentials, options=options)
        try:
            grpc.channel_ready_future(probe_channel).result(
                timeout=self._settings.fabric_timeout_seconds
            )
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return FabricHealthStatus(
                status="connected",
                channel=channel_name,
                chaincode=chaincode_name,
                msp_id=msp_id,
                peer_endpoint=peer_endpoint,
                message="Fabric Gateway peer is reachable.",
                latency_ms=latency_ms,
            )
        except grpc.FutureTimeoutError:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return FabricHealthStatus(
                status="unavailable",
                channel=channel_name,
                chaincode=chaincode_name,
                msp_id=msp_id,
                peer_endpoint=peer_endpoint,
                message=(
                    f"Fabric Gateway peer at '{peer_endpoint}' did not respond within "
                    f"{self._settings.fabric_timeout_seconds}s."
                ),
                latency_ms=latency_ms,
            )
        finally:
            probe_channel.close()

    # -----------------------------------------------------------------
    # Transactions
    # -----------------------------------------------------------------

    def evaluate_transaction(self, name: str, *args: str) -> str:
        """Evaluate (query) a chaincode function via the Gateway ``Evaluate`` RPC.

        Read-only: never touches the ordering service, never mutates ledger
        state.

        Args:
            name: Chaincode transaction/function name (e.g. ``GetDeviceAnchor``).
            *args: String arguments passed to the chaincode function, in order.

        Returns:
            The UTF-8 decoded response payload (empty string if the chaincode
            returned no payload).

        Raises:
            FabricNotConfigured: Fabric is disabled.
            FabricUnavailable: The peer is unreachable.
            FabricQueryError: The chaincode returned an error, or the RPC
                failed for a non-connectivity reason.
        """
        self._ensure_connected()
        assert self._stub is not None  # narrows type after _ensure_connected

        tx_id, signed_proposal = self._new_signed_proposal(name, args)
        request = gateway_pb2.EvaluateRequest(
            transaction_id=tx_id,
            channel_id=self._settings.fabric_channel_name,
            proposed_transaction=signed_proposal,
        )

        t_start = time.perf_counter()
        try:
            response = self._stub.Evaluate(
                request, timeout=self._settings.fabric_timeout_seconds
            )
        except grpc.RpcError as exc:
            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            self._handle_rpc_error(
                exc, operation=f"Evaluate({name})", latency_ms=latency_ms, query=True
            )
            raise  # _handle_rpc_error always raises; appeases type checkers

        latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
        payload = (
            response.result.payload.decode("utf-8") if response.result.payload else ""
        )
        logger.bind(
            channel=self._settings.fabric_channel_name,
            chaincode=self._settings.fabric_chaincode_name,
            transaction=name,
            device_id=args[0] if args else None,
            latency_ms=latency_ms,
            result="success",
        ).info("Fabric evaluate_transaction complete.")
        return payload

    def submit_transaction(self, name: str, *args: str) -> str:
        """Submit (endorse, order, commit) a chaincode write via the Gateway.

        Performs the full Endorse -> sign -> Submit -> CommitStatus flow in a
        single pass. Never retried by this method: a caller that wants retry
        semantics must decide, above this layer, whether re-submitting after
        a failure risks a duplicate on-chain write (P6.2 does not add such a
        policy — see the report's "Retry / resilience" section).

        Args:
            name: Chaincode transaction name (e.g. ``AnchorDevicePassport``).
            *args: String arguments passed to the chaincode function, in order.

        Returns:
            The Fabric transaction ID once committed with a VALID status code.

        Raises:
            FabricNotConfigured: Fabric is disabled.
            FabricUnavailable: The peer is unreachable.
            FabricTransactionError: Endorsement, submission, or commit failed,
                or the transaction committed with a non-VALID status code.
        """
        self._ensure_connected()
        assert self._stub is not None

        tx_id, signed_proposal = self._new_signed_proposal(name, args)
        t_start = time.perf_counter()

        endorse_request = gateway_pb2.EndorseRequest(
            transaction_id=tx_id,
            channel_id=self._settings.fabric_channel_name,
            proposed_transaction=signed_proposal,
        )
        try:
            endorse_response = self._stub.Endorse(
                endorse_request, timeout=self._settings.fabric_timeout_seconds
            )
        except grpc.RpcError as exc:
            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            self._handle_rpc_error(
                exc, operation=f"Endorse({name})", latency_ms=latency_ms, query=False
            )
            raise

        prepared = endorse_response.prepared_transaction
        signed_envelope = common_pb2.Envelope(
            payload=prepared.payload,
            signature=self._sign(prepared.payload),
        )

        submit_request = gateway_pb2.SubmitRequest(
            transaction_id=tx_id,
            channel_id=self._settings.fabric_channel_name,
            prepared_transaction=signed_envelope,
        )
        try:
            self._stub.Submit(
                submit_request, timeout=self._settings.fabric_timeout_seconds
            )
        except grpc.RpcError as exc:
            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            self._handle_rpc_error(
                exc, operation=f"Submit({name})", latency_ms=latency_ms, query=False
            )
            raise

        commit_status_request = gateway_pb2.CommitStatusRequest(
            transaction_id=tx_id,
            channel_id=self._settings.fabric_channel_name,
            identity=self._creator_bytes,
        )
        serialized_request = commit_status_request.SerializeToString()
        signed_commit_status_request = gateway_pb2.SignedCommitStatusRequest(
            request=serialized_request,
            signature=self._sign(serialized_request),
        )
        try:
            commit_response = self._stub.CommitStatus(
                signed_commit_status_request,
                timeout=self._settings.fabric_timeout_seconds,
            )
        except grpc.RpcError as exc:
            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            self._handle_rpc_error(
                exc,
                operation=f"CommitStatus({name})",
                latency_ms=latency_ms,
                query=False,
            )
            raise

        latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
        if commit_response.result != transaction_pb2.TxValidationCode.VALID:
            code_name = transaction_pb2.TxValidationCode.Name(commit_response.result)
            logger.bind(
                channel=self._settings.fabric_channel_name,
                chaincode=self._settings.fabric_chaincode_name,
                transaction=name,
                device_id=args[0] if args else None,
                latency_ms=latency_ms,
                result="invalid",
                validation_code=code_name,
            ).error("Fabric submit_transaction committed with a non-VALID status.")
            raise FabricTransactionError(
                f"Transaction '{tx_id}' committed with validation code "
                f"{code_name}, not VALID.",
                details={
                    "transaction_id": tx_id,
                    "validation_code": code_name,
                    "block_number": commit_response.block_number,
                },
            )

        logger.bind(
            channel=self._settings.fabric_channel_name,
            chaincode=self._settings.fabric_chaincode_name,
            transaction=name,
            device_id=args[0] if args else None,
            latency_ms=latency_ms,
            result="success",
            block_number=commit_response.block_number,
        ).info("Fabric submit_transaction committed VALID.")
        return tx_id

    # -----------------------------------------------------------------
    # Backward-compatible duck-typed aliases
    #
    # `FabricExternalTrustLedger.anchor()` / `.get_anchor()` (P5.11, unchanged
    # by P6.2) call `self._client.submitTransaction(name, *args)` and
    # `self._client.evaluateTransaction(name, *args)` — the mock-client
    # convention locked in by `test_fabric_live_client_adapter_invocations`.
    # These aliases let a `FabricGatewayClient` be injected as that adapter's
    # `gateway_client` unchanged.
    # -----------------------------------------------------------------

    def submitTransaction(  # noqa: N802 - external adapter contract
        self, name: str, *args: str
    ) -> str:
        """Alias for :meth:`submit_transaction` (P5.11 adapter interface).

        Also records a Fabric transaction outcome (P7.3) — this is the
        actual call surface used by ``FabricExternalTrustLedger``, so it is
        the one low-risk place to observe every real transaction attempt
        without touching the underlying Endorse/sign/Submit/CommitStatus
        implementation in :meth:`submit_transaction`.
        """
        try:
            result = self.submit_transaction(name, *args)
        except Exception:
            get_metrics_registry().record_fabric_transaction(succeeded=False)
            raise
        get_metrics_registry().record_fabric_transaction(succeeded=True)
        return result

    def evaluateTransaction(  # noqa: N802 - external adapter contract
        self, name: str, *args: str
    ) -> str:
        """Alias for :meth:`evaluate_transaction` (P5.11 adapter interface).

        Also records a Fabric transaction outcome (P7.3) — see
        :meth:`submitTransaction` for why this wrapper, not the internal
        implementation, is the observation point.
        """
        try:
            result = self.evaluate_transaction(name, *args)
        except Exception:
            get_metrics_registry().record_fabric_transaction(succeeded=False)
            raise
        get_metrics_registry().record_fabric_transaction(succeeded=True)
        return result

    # -----------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------

    def _ensure_connected(self) -> None:
        """Connect on first use if not already connected; raise if unreachable."""
        if not self._settings.fabric_enabled:
            raise FabricNotConfigured(
                "Fabric Gateway is disabled (FABRIC_ENABLED=false).",
                details={"channel": self._settings.fabric_channel_name},
            )
        if self._state != FabricConnectionState.CONNECTED or self._channel is None:
            self.connect()

    def _peer_host(self) -> str:
        """Return the hostname portion of `fabric_peer_endpoint` for TLS SNI."""
        endpoint = self._settings.fabric_peer_endpoint
        return endpoint.rsplit(":", 1)[0] if endpoint else ""

    def _build_channel_credentials(self) -> grpc.ChannelCredentials:
        """Build TLS channel credentials from the configured CA certificate.

        Raises:
            FabricConfigurationError: The configured TLS CA path is missing
                or the file cannot be read.
        """
        cert_path = self._settings.fabric_tls_cert_path
        if not cert_path:
            raise FabricConfigurationError(
                "FABRIC_TLS_CERT_PATH is not configured; a TLS root certificate is "
                "required to connect to a Fabric peer (no insecure fallback).",
                details={"peer_endpoint": self._settings.fabric_gateway_peer_endpoint},
            )
        path = Path(cert_path)
        if not path.is_file():
            raise FabricConfigurationError(
                "Configured FABRIC_TLS_CERT_PATH does not exist.",
                details={"path": str(path)},
            )
        try:
            ca_bytes = path.read_bytes()
        except OSError as exc:
            raise FabricConfigurationError(
                "Configured FABRIC_TLS_CERT_PATH could not be read.",
                details={"path": str(path)},
            ) from exc
        return grpc.ssl_channel_credentials(root_certificates=ca_bytes)

    def _load_identity(self) -> None:
        """Load and cache the client's X.509 identity certificate and EC private key.

        Idempotent (a no-op once cached). Never logs certificate or key
        contents — only file paths and the class of failure.

        Raises:
            FabricConfigurationError: A path is unset/missing, or the file
                content is not a parseable X.509 certificate / EC private key.
        """
        if self._identity_cert is not None and self._identity_key is not None:
            return

        cert_path = self._settings.fabric_identity_cert_path
        key_path = self._settings.fabric_identity_key_path
        if not cert_path or not key_path:
            raise FabricConfigurationError(
                "FABRIC_IDENTITY_CERT_PATH and FABRIC_IDENTITY_KEY_PATH must both be "
                "configured to submit or evaluate Fabric transactions.",
                details={
                    "cert_path_configured": bool(cert_path),
                    "key_path_configured": bool(key_path),
                },
            )

        cert_file = Path(cert_path)
        key_file = Path(key_path)
        if not cert_file.is_file():
            raise FabricConfigurationError(
                "Configured FABRIC_IDENTITY_CERT_PATH does not exist.",
                details={"path": str(cert_file)},
            )
        if not key_file.is_file():
            raise FabricConfigurationError(
                "Configured FABRIC_IDENTITY_KEY_PATH does not exist.",
                details={"path": str(key_file)},
            )

        try:
            cert_pem = cert_file.read_bytes()
            certificate = x509.load_pem_x509_certificate(cert_pem)
        except (OSError, ValueError) as exc:
            raise FabricConfigurationError(
                "Configured FABRIC_IDENTITY_CERT_PATH is not a readable PEM "
                "X.509 certificate.",
                details={"path": str(cert_file)},
            ) from exc

        try:
            key_pem = key_file.read_bytes()
            private_key = serialization.load_pem_private_key(key_pem, password=None)
        except (OSError, ValueError, TypeError) as exc:
            raise FabricConfigurationError(
                "Configured FABRIC_IDENTITY_KEY_PATH is not a readable, "
                "unencrypted PEM private key.",
                details={"path": str(key_file)},
            ) from exc
        finally:
            key_pem = b""  # best-effort: drop the reference to key bytes promptly

        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise FabricConfigurationError(
                "Configured FABRIC_IDENTITY_KEY_PATH must be an elliptic-curve private "
                "key (Fabric MSP identities are ECDSA).",
                details={"path": str(key_file)},
            )

        self._identity_cert = certificate
        self._identity_key = private_key
        self._creator_bytes = identities_pb2.SerializedIdentity(
            mspid=self._settings.fabric_msp_id,
            id_bytes=cert_pem,
        ).SerializeToString()

    def _sign(self, data: bytes) -> bytes:
        """Sign ``data`` with the client identity's EC private key.

        Produces a DER-encoded ECDSA/SHA-256 signature normalized to low-S
        form, matching Fabric's malleability-resistant signature convention
        (every official Fabric SDK does this same normalization).
        """
        assert self._identity_key is not None  # _load_identity() always runs first
        signature = self._identity_key.sign(data, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(signature)
        order = _CURVE_ORDERS.get(type(self._identity_key.curve))
        if order is not None and s > order // 2:
            s = order - s
        return encode_dss_signature(r, s)

    def _new_signed_proposal(
        self, function_name: str, args: tuple[str, ...]
    ) -> tuple[str, proposal_pb2.SignedProposal]:
        """Build and sign a Fabric transaction proposal for `function_name(*args)`.

        Returns the derived transaction ID and the signed proposal, following
        Fabric's standard client-side proposal construction: a random nonce,
        `tx_id = sha256(nonce || creator)`, a `ChannelHeader` +
        `SignatureHeader` wrapping a `ChaincodeInvocationSpec`, signed with
        the client identity's private key.
        """
        self._load_identity()
        assert self._creator_bytes is not None

        nonce = os.urandom(24)
        tx_id = hashlib.sha256(nonce + self._creator_bytes).hexdigest()

        timestamp = Timestamp()
        timestamp.FromDatetime(_utc_now())

        channel_header = common_pb2.ChannelHeader(
            type=common_pb2.HeaderType.ENDORSER_TRANSACTION,
            version=1,
            timestamp=timestamp,
            channel_id=self._settings.fabric_channel_name,
            tx_id=tx_id,
            epoch=0,
            extension=proposal_pb2.ChaincodeHeaderExtension(
                chaincode_id=chaincode_pb2.ChaincodeID(
                    name=self._settings.fabric_chaincode_name
                )
            ).SerializeToString(),
        )
        signature_header = common_pb2.SignatureHeader(
            creator=self._creator_bytes, nonce=nonce
        )
        header = common_pb2.Header(
            channel_header=channel_header.SerializeToString(),
            signature_header=signature_header.SerializeToString(),
        )

        chaincode_input = chaincode_pb2.ChaincodeInput(
            args=[function_name.encode("utf-8"), *(arg.encode("utf-8") for arg in args)]
        )
        invocation_spec = chaincode_pb2.ChaincodeInvocationSpec(
            chaincode_spec=chaincode_pb2.ChaincodeSpec(
                type=chaincode_pb2.ChaincodeSpec.Type.GOLANG,
                chaincode_id=chaincode_pb2.ChaincodeID(
                    name=self._settings.fabric_chaincode_name
                ),
                input=chaincode_input,
            )
        )
        proposal_payload = proposal_pb2.ChaincodeProposalPayload(
            input=invocation_spec.SerializeToString()
        )

        proposal = proposal_pb2.Proposal(
            header=header.SerializeToString(),
            payload=proposal_payload.SerializeToString(),
        )
        proposal_bytes = proposal.SerializeToString()
        signed_proposal = proposal_pb2.SignedProposal(
            proposal_bytes=proposal_bytes,
            signature=self._sign(proposal_bytes),
        )
        return tx_id, signed_proposal

    def _handle_rpc_error(
        self, exc: grpc.RpcError, *, operation: str, latency_ms: float, query: bool
    ) -> None:
        """Classify a gRPC failure into the appropriate Fabric exception and raise."""
        code = exc.code() if hasattr(exc, "code") else None
        details = exc.details() if hasattr(exc, "details") else str(exc)
        logger.bind(
            channel=self._settings.fabric_channel_name,
            chaincode=self._settings.fabric_chaincode_name,
            operation=operation,
            latency_ms=latency_ms,
            result="error",
            grpc_code=str(code),
        ).error("Fabric Gateway RPC failed.")

        if code in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
            self._state = FabricConnectionState.ERROR
            raise FabricUnavailable(
                f"Fabric Gateway peer unreachable during {operation}: {details}",
                details={"operation": operation, "grpc_code": str(code)},
            ) from exc

        error_cls = FabricQueryError if query else FabricTransactionError
        raise error_cls(
            f"Fabric Gateway {operation} failed: {details}",
            details={"operation": operation, "grpc_code": str(code)},
        ) from exc


# NIST P-256 (secp256r1) and P-384 (secp384r1) group orders, needed for
# Fabric's low-S ECDSA signature normalization. Fabric MSP identities are
# conventionally P-256; P-384 is included for completeness/documentation.
_CURVE_ORDERS: dict[type, int] = {
    ec.SECP256R1: 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551,
    ec.SECP384R1: int(
        "ffffffffffffffffffffffffffffffffffffffffffffffff"
        "c7634d81f4372ddf581a0db248b0a77aecec196accc52973",
        16,
    ),
}


def build_fabric_gateway_client(settings: Settings) -> FabricGatewayClient | None:
    """Construct a :class:`FabricGatewayClient` from settings, or ``None`` if disabled.

    Never connects eagerly: construction only reads configuration, so a
    process can start up (and this factory can run at dependency-injection
    time) even when no Fabric peer is currently reachable. The client
    connects lazily on its first real ``submit_transaction`` /
    ``evaluate_transaction`` call, raising a classified
    :class:`~device_ai.exceptions.FabricGatewayError` at that point if the
    peer cannot be reached — never silently, never by fabricating success.

    Args:
        settings: Active application settings.

    Returns:
        A configured (not-yet-connected) :class:`FabricGatewayClient` when
        ``settings.fabric_enabled`` is True, otherwise ``None`` — mirroring
        the pre-P6.2 behavior of an unconfigured
        :class:`~device_ai.devices.external_trust.FabricExternalTrustLedger`
        (``gateway_client=None``, honestly reports UNAVAILABLE).
    """
    if not settings.fabric_enabled:
        return None
    return FabricGatewayClient(settings)
