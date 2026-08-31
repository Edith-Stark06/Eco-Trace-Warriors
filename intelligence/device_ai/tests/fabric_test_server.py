"""In-process fake Fabric Gateway gRPC server, for P6.2 tests only.

Implements the real ``gateway.Gateway`` gRPC service contract (compiled from
the vendored, unmodified upstream protos in ``blockchain/fabric-protos/``)
over a genuine local TLS gRPC connection. This validates
:class:`~device_ai.devices.fabric_gateway_client.FabricGatewayClient`'s TLS
channel construction, identity loading, proposal/envelope construction, and
ECDSA signing end-to-end against a real (if not Fabric-specific) peer —
without needing Docker or an actual Hyperledger Fabric network.

What this does NOT validate: Fabric-specific business logic a real peer
performs (MSP/identity membership validation, endorsement policy
satisfaction, chaincode execution, ledger commit semantics). This server
returns configurable canned responses; see ``reports/P6_2_FABRIC_GATEWAY_INTEGRATION.md``
for the honest scope of what P6.2 could and could not verify.
"""

from __future__ import annotations

import datetime
import sys
from collections.abc import Callable
from concurrent import futures
from dataclasses import dataclass
from pathlib import Path

import grpc
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

_PB_ROOT = str(Path(__file__).resolve().parents[1] / "devices" / "fabric_pb")
if _PB_ROOT not in sys.path:
    sys.path.insert(0, _PB_ROOT)

from common import common_pb2  # noqa: E402
from gateway import gateway_pb2, gateway_pb2_grpc  # noqa: E402
from peer import proposal_response_pb2, transaction_pb2  # noqa: E402


@dataclass
class GeneratedIdentity:
    """A self-signed EC identity: certificate + private key, both PEM bytes."""

    cert_pem: bytes
    key_pem: bytes


def generate_self_signed_identity(common_name: str) -> GeneratedIdentity:
    """Generate a fresh, ephemeral self-signed EC (P-256) certificate + key.

    Test-only. Used both for the fake server's TLS certificate and for the
    client identity certificate presented to it — neither is ever committed
    to the repository (generated fresh in memory / tmp_path per test run).
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False
        )
        .sign(private_key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return GeneratedIdentity(cert_pem=cert_pem, key_pem=key_pem)


@dataclass
class FakeGatewayBehavior:
    """Configurable canned behavior for :class:`FakeGatewayServicer`.

    When ``simulate_chaincode`` is True (the default), the servicer ignores
    ``evaluate_payload`` and instead behaves like a minimal, stateful
    replica of the P6.1 ``ecotrace-lifecycle`` chaincode's
    ``AnchorDevicePassport`` / ``GetDeviceAnchor`` pair: an ``Endorse`` for
    ``AnchorDevicePassport`` records ``{deviceId: {passportFingerprint,
    algorithm, transactionId, anchoredAt}}`` in ``FakeGatewayServicer.anchors``
    (simplification: recorded at endorsement time, not gated on the later
    commit status — sufficient for exercising the client's round trip, not a
    claim about real Fabric's atomicity), and an ``Evaluate`` for
    ``GetDeviceAnchor`` returns that device's JSON record (or the literal
    string ``"null"``), exactly matching the real chaincode's response shape
    (see ``blockchain/chaincode/ecotrace-lifecycle/src/ecotrace-lifecycle.ts``).
    """

    simulate_chaincode: bool = True
    evaluate_payload: bytes = (
        b'{"deviceId":"DEV-01","passportFingerprint":"'
        + b"a" * 64
        + b'","algorithm":"sha256","anchoredAt":"2026-01-01T00:00:00Z","transactionId":"tx-fake-001"}'
    )
    evaluate_status: int = 200
    evaluate_error: grpc.StatusCode | None = None
    commit_result: int = transaction_pb2.TxValidationCode.VALID
    commit_block_number: int = 42
    submit_error: grpc.StatusCode | None = None
    endorse_error: grpc.StatusCode | None = None
    commit_error: grpc.StatusCode | None = None
    on_evaluate: Callable[[gateway_pb2.EvaluateRequest], None] | None = None
    on_submit: Callable[[gateway_pb2.SubmitRequest], None] | None = None


def _extract_function_and_args(proposal_bytes: bytes) -> tuple[str, list[str]]:
    """Parse a serialized `Proposal`'s chaincode function name and string args."""
    from peer import chaincode_pb2, proposal_pb2

    proposal = proposal_pb2.Proposal.FromString(proposal_bytes)
    cc_proposal_payload = proposal_pb2.ChaincodeProposalPayload.FromString(
        proposal.payload
    )
    invocation_spec = chaincode_pb2.ChaincodeInvocationSpec.FromString(
        cc_proposal_payload.input
    )
    raw_args = list(invocation_spec.chaincode_spec.input.args)
    decoded = [a.decode("utf-8") for a in raw_args]
    return (decoded[0], decoded[1:]) if decoded else ("", [])


class FakeGatewayServicer(gateway_pb2_grpc.GatewayServicer):
    """Minimal, protocol-real implementation of the Fabric ``Gateway`` service."""

    def __init__(self, behavior: FakeGatewayBehavior) -> None:
        self.behavior = behavior
        self.submitted_envelopes: list[common_pb2.Envelope] = []
        self.commit_status_requests: list[gateway_pb2.CommitStatusRequest] = []
        self.anchors: dict[str, dict[str, str]] = {}

    def Evaluate(  # noqa: N802
        self, request: gateway_pb2.EvaluateRequest, context: grpc.ServicerContext
    ) -> gateway_pb2.EvaluateResponse:
        if self.behavior.on_evaluate is not None:
            self.behavior.on_evaluate(request)
        if self.behavior.evaluate_error is not None:
            context.abort(self.behavior.evaluate_error, "simulated evaluate failure")

        if self.behavior.simulate_chaincode:
            import json as _json

            fn, args = _extract_function_and_args(
                request.proposed_transaction.proposal_bytes
            )
            if fn == "GetDeviceAnchor" and args:
                record = self.anchors.get(args[0])
                payload = _json.dumps(record).encode("utf-8") if record else b"null"
            else:
                payload = b"null"
            return gateway_pb2.EvaluateResponse(
                result=proposal_response_pb2.Response(
                    status=200, message="OK", payload=payload
                )
            )

        return gateway_pb2.EvaluateResponse(
            result=proposal_response_pb2.Response(
                status=self.behavior.evaluate_status,
                message="OK",
                payload=self.behavior.evaluate_payload,
            )
        )

    def Endorse(  # noqa: N802
        self, request: gateway_pb2.EndorseRequest, context: grpc.ServicerContext
    ) -> gateway_pb2.EndorseResponse:
        if self.behavior.endorse_error is not None:
            context.abort(self.behavior.endorse_error, "simulated endorse failure")

        if self.behavior.simulate_chaincode:
            fn, args = _extract_function_and_args(
                request.proposed_transaction.proposal_bytes
            )
            if fn == "AnchorDevicePassport" and len(args) >= 2:
                device_id, fingerprint = args[0], args[1]
                algorithm = args[2] if len(args) > 2 else "sha256"
                self.anchors[device_id] = {
                    "deviceId": device_id,
                    "passportFingerprint": fingerprint.lower(),
                    "algorithm": algorithm.lower(),
                    "anchoredAt": "2026-01-01T00:00:00.000Z",
                    "transactionId": f"fake-tx-{len(self.anchors) + 1}",
                }
        # Real peers return a Payload(header=<proposal header>, data=<Transaction>)
        # wrapped in an unsigned Envelope. For this fake, the header is echoed
        # back verbatim (it is already correctly constructed by the client)
        # and `data` is a placeholder — the client never inspects `data`, it
        # only re-signs `payload` bytes as-is, exactly like a real Fabric SDK.
        # (`common.Payload.header` is an embedded `Header` message, unlike
        # `peer.Proposal.header`/`.payload`, which are opaque `bytes`.)
        payload = common_pb2.Payload(
            header=common_pb2.Header.FromString(
                _extract_header_bytes(request.proposed_transaction.proposal_bytes)
            ),
            data=b"fake-endorsed-transaction-data",
        )
        envelope = common_pb2.Envelope(payload=payload.SerializeToString())
        return gateway_pb2.EndorseResponse(prepared_transaction=envelope)

    def Submit(  # noqa: N802
        self, request: gateway_pb2.SubmitRequest, context: grpc.ServicerContext
    ) -> gateway_pb2.SubmitResponse:
        if self.behavior.submit_error is not None:
            context.abort(self.behavior.submit_error, "simulated submit failure")
        if not request.prepared_transaction.signature:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "prepared_transaction was not signed by the client",
            )
        if self.behavior.on_submit is not None:
            self.behavior.on_submit(request)
        self.submitted_envelopes.append(request.prepared_transaction)
        return gateway_pb2.SubmitResponse()

    def CommitStatus(  # noqa: N802
        self,
        request: gateway_pb2.SignedCommitStatusRequest,
        context: grpc.ServicerContext,
    ) -> gateway_pb2.CommitStatusResponse:
        if self.behavior.commit_error is not None:
            context.abort(self.behavior.commit_error, "simulated commit-status failure")
        if not request.signature:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "CommitStatusRequest was not signed by the client",
            )
        parsed = gateway_pb2.CommitStatusRequest.FromString(request.request)
        self.commit_status_requests.append(parsed)
        return gateway_pb2.CommitStatusResponse(
            result=self.behavior.commit_result,
            block_number=self.behavior.commit_block_number,
        )


def _extract_header_bytes(proposal_bytes: bytes) -> bytes:
    """Pull the serialized `common.Header` out of a serialized `Proposal`."""
    from peer import proposal_pb2

    proposal = proposal_pb2.Proposal.FromString(proposal_bytes)
    return proposal.header


class FakeFabricGateway:
    """Runs :class:`FakeGatewayServicer` on a background thread over local TLS.

    Usage (as a context manager)::

        server_identity = generate_self_signed_identity("localhost")
        with FakeFabricGateway(server_identity, FakeGatewayBehavior()) as fake:
            settings = Settings(
                fabric_enabled=True,
                fabric_gateway_peer_endpoint=fake.address,
                fabric_peer_endpoint=fake.address,
                fabric_tls_cert_path=str(fake.ca_cert_path),
                fabric_identity_cert_path=str(client_cert_path),
                fabric_identity_key_path=str(client_key_path),
            )
            client = FabricGatewayClient(settings)
            ...
    """

    def __init__(
        self,
        server_identity: GeneratedIdentity,
        behavior: FakeGatewayBehavior,
        tmp_path: Path,
    ) -> None:
        self.behavior = behavior
        self.servicer = FakeGatewayServicer(behavior)
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        gateway_pb2_grpc.add_GatewayServicer_to_server(self.servicer, self._server)

        credentials = grpc.ssl_server_credentials(
            [(server_identity.key_pem, server_identity.cert_pem)]
        )
        self.port = self._server.add_secure_port("localhost:0", credentials)
        self.address = f"localhost:{self.port}"

        self.ca_cert_path = tmp_path / "fake_gateway_ca.pem"
        self.ca_cert_path.write_bytes(server_identity.cert_pem)

    def __enter__(self) -> FakeFabricGateway:
        self._server.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._server.stop(grace=None)
