"""External and Blockchain Trust Ledger Abstraction (P5.11).

Provides an external/verifiable blockchain trust layer that interfaces with
Hyperledger Fabric, deterministic in-memory reference ledgers, and future
distributed trust providers without replacing local operational trust.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import json
from typing import Any, Protocol, runtime_checkable
import uuid

from loguru import logger

from ..configs.settings import Settings, get_settings
from ..exceptions import (
    AnchorConflictError,
    ExternalAnchorConflictError,
    ExternalAnchorNotFoundError,
    ExternalLedgerError,
    ExternalLedgerUnavailableError,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ExternalTrustStatus(str, Enum):
    """Evaluation status of an external / blockchain trust verification."""

    NOT_ANCHORED = "NOT_ANCHORED"  #: Device is not anchored on external ledger.
    VERIFIED = "VERIFIED"          #: External ledger anchor matches current passport fingerprint and algorithm.
    MISMATCH = "MISMATCH"          #: Fingerprint or algorithm on external ledger differs from current passport.
    UNAVAILABLE = "UNAVAILABLE"    #: External ledger provider is unreachable or disabled.
    ERROR = "ERROR"                #: Unexpected provider error during evaluation.


@dataclass(frozen=True, slots=True)
class ExternalTrustAnchor:
    """Immutable domain representation of an external / blockchain trust anchor."""

    external_anchor_id: str
    device_id: str
    passport_fingerprint: str
    algorithm: str = "sha256"
    provider: str = "memory"
    network: str = "ecotrace-channel"
    transaction_id: str = field(default_factory=lambda: f"tx-{uuid.uuid4().hex[:16]}")
    anchored_at: str = field(default_factory=lambda: _utc_now().isoformat())
    status: str = "ANCHORED"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert external trust anchor to a JSON-serializable dictionary."""
        return {
            "external_anchor_id": self.external_anchor_id,
            "device_id": self.device_id,
            "passport_fingerprint": self.passport_fingerprint,
            "algorithm": self.algorithm,
            "provider": self.provider,
            "network": self.network,
            "transaction_id": self.transaction_id,
            "anchored_at": self.anchored_at,
            "status": self.status,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class ExternalTrustVerificationResult:
    """Result of verifying current passport fingerprint against external ledger record."""

    device_id: str
    status: ExternalTrustStatus
    stored_fingerprint: str | None
    current_fingerprint: str | None
    algorithm: str = "sha256"
    provider: str = "memory"
    network: str = "ecotrace-channel"
    transaction_id: str | None = None
    anchored_at: str | None = None
    verified_at: str = field(default_factory=lambda: _utc_now().isoformat())
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert verification result to a JSON-serializable dictionary."""
        return {
            "device_id": self.device_id,
            "status": self.status.value,
            "stored_fingerprint": self.stored_fingerprint,
            "current_fingerprint": self.current_fingerprint,
            "algorithm": self.algorithm,
            "provider": self.provider,
            "network": self.network,
            "transaction_id": self.transaction_id,
            "anchored_at": self.anchored_at,
            "verified_at": self.verified_at,
            "message": self.message,
            "details": self.details,
        }


@dataclass(frozen=True, slots=True)
class FullTrustComparisonResult:
    """Synthesized comparison across Local Operational Trust and External Blockchain Trust."""

    device_id: str
    local_status: str
    external_status: str
    overall_status: str
    passport_fingerprint: str | None
    local_anchored_fingerprint: str | None
    external_anchored_fingerprint: str | None
    local_anchor_id: str | None
    external_anchor_id: str | None
    transaction_id: str | None
    provider: str
    network: str
    evaluated_at: str = field(default_factory=lambda: _utc_now().isoformat())
    reason: str = ""
    local_trust_details: dict[str, Any] = field(default_factory=dict)
    external_trust_details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert aggregate trust result to a JSON-serializable dictionary."""
        return {
            "device_id": self.device_id,
            "local_status": self.local_status,
            "external_status": self.external_status,
            "overall_status": self.overall_status,
            "passport_fingerprint": self.passport_fingerprint,
            "local_anchored_fingerprint": self.local_anchored_fingerprint,
            "external_anchored_fingerprint": self.external_anchored_fingerprint,
            "local_anchor_id": self.local_anchor_id,
            "external_anchor_id": self.external_anchor_id,
            "transaction_id": self.transaction_id,
            "provider": self.provider,
            "network": self.network,
            "evaluated_at": self.evaluated_at,
            "reason": self.reason,
            "local_trust_details": self.local_trust_details,
            "external_trust_details": self.external_trust_details,
        }


def compute_overall_trust_status(
    local_status: str,
    external_status: str,
) -> str:
    """Compute aggregate trust status from local operational status and external ledger status.

    Precedence Hierarchy:
    1. If either local or external is MISMATCH -> MISMATCH
    2. If local is STALE -> STALE
    3. If local is UNANCHORED -> UNANCHORED
    4. If local is VERIFIED and external is VERIFIED -> VERIFIED
    5. If local is VERIFIED and external is (NOT_ANCHORED / UNAVAILABLE) -> VERIFIED (with local guarantee)
    6. Fallback -> local_status
    """
    if local_status == "MISMATCH" or external_status == "MISMATCH":
        return "MISMATCH"
    if local_status == "STALE":
        return "STALE"
    if local_status == "UNANCHORED":
        return "UNANCHORED"
    if local_status == "VERIFIED":
        return "VERIFIED"
    return local_status


@runtime_checkable
class ExternalTrustLedger(Protocol):
    """Storage-agnostic protocol defining operations on an external / blockchain trust ledger."""

    def anchor(self, anchor: ExternalTrustAnchor, overwrite: bool = False) -> ExternalTrustAnchor:
        """Submit and record an anchor on the external ledger."""
        ...

    def get_anchor(self, device_id: str) -> ExternalTrustAnchor | None:
        """Retrieve stored anchor from the external ledger."""
        ...

    def verify_anchor(
        self,
        device_id: str,
        current_fingerprint: str,
        algorithm: str = "sha256",
    ) -> ExternalTrustVerificationResult:
        """Verify current fingerprint against external ledger record."""
        ...

    def is_available(self) -> bool:
        """Check if external ledger provider is reachable and active."""
        ...


class InMemoryExternalTrustLedger:
    """Deterministic in-memory reference ledger adapter for local development and testing."""

    def __init__(self, network: str = "ecotrace-channel", provider: str = "memory") -> None:
        self._network = network
        self._provider = provider
        self._anchors: dict[str, ExternalTrustAnchor] = {}

    def is_available(self) -> bool:
        """Reference in-memory provider is always available."""
        return True

    def anchor(self, anchor: ExternalTrustAnchor, overwrite: bool = False) -> ExternalTrustAnchor:
        """Persist an external trust anchor in the reference store."""
        existing = self._anchors.get(anchor.device_id)
        if existing is not None and not overwrite:
            if existing.passport_fingerprint == anchor.passport_fingerprint:
                logger.bind(device_id=anchor.device_id).info("Idempotent external anchor request.")
                return existing

            raise ExternalAnchorConflictError(
                f"External anchor conflict: device '{anchor.device_id}' is already anchored on external ledger "
                f"with fingerprint '{existing.passport_fingerprint}'; cannot overwrite with '{anchor.passport_fingerprint}'.",
                details={
                    "device_id": anchor.device_id,
                    "existing_fingerprint": existing.passport_fingerprint,
                    "new_fingerprint": anchor.passport_fingerprint,
                },
            )

        self._anchors[anchor.device_id] = anchor
        logger.bind(device_id=anchor.device_id, tx_id=anchor.transaction_id).info(
            "External trust anchor recorded in reference ledger."
        )
        return anchor

    def get_anchor(self, device_id: str) -> ExternalTrustAnchor | None:
        """Retrieve external anchor by device_id."""
        return self._anchors.get(device_id)

    def verify_anchor(
        self,
        device_id: str,
        current_fingerprint: str,
        algorithm: str = "sha256",
    ) -> ExternalTrustVerificationResult:
        """Verify fingerprint against reference ledger."""
        eval_time = _utc_now().isoformat()
        stored = self._anchors.get(device_id)

        if stored is None:
            return ExternalTrustVerificationResult(
                device_id=device_id,
                status=ExternalTrustStatus.NOT_ANCHORED,
                stored_fingerprint=None,
                current_fingerprint=current_fingerprint,
                algorithm=algorithm,
                provider=self._provider,
                network=self._network,
                transaction_id=None,
                anchored_at=None,
                verified_at=eval_time,
                message=f"Device '{device_id}' has not been anchored on external ledger '{self._network}'.",
                details={"provider": self._provider, "network": self._network},
            )

        if stored.passport_fingerprint == current_fingerprint and stored.algorithm == algorithm:
            return ExternalTrustVerificationResult(
                device_id=device_id,
                status=ExternalTrustStatus.VERIFIED,
                stored_fingerprint=stored.passport_fingerprint,
                current_fingerprint=current_fingerprint,
                algorithm=algorithm,
                provider=self._provider,
                network=self._network,
                transaction_id=stored.transaction_id,
                anchored_at=stored.anchored_at,
                verified_at=eval_time,
                message="External ledger anchor verified: fingerprint and algorithm match recorded state.",
                details={"external_anchor_id": stored.external_anchor_id, "metadata": stored.metadata},
            )

        return ExternalTrustVerificationResult(
            device_id=device_id,
            status=ExternalTrustStatus.MISMATCH,
            stored_fingerprint=stored.passport_fingerprint,
            current_fingerprint=current_fingerprint,
            algorithm=algorithm,
            provider=self._provider,
            network=self._network,
            transaction_id=stored.transaction_id,
            anchored_at=stored.anchored_at,
            verified_at=eval_time,
            message="External ledger fingerprint MISMATCH: recorded on-chain state differs from current passport.",
            details={
                "external_anchor_id": stored.external_anchor_id,
                "stored_fingerprint": stored.passport_fingerprint,
                "current_fingerprint": current_fingerprint,
            },
        )

    def count(self) -> int:
        """Return total count of anchors in reference ledger."""
        return len(self._anchors)

    def clear(self) -> None:
        """Clear all anchors in reference ledger."""
        self._anchors.clear()


class FabricExternalTrustLedger:
    """Hyperledger Fabric ledger adapter (P5.11).

    Interfaces with Hyperledger Fabric gateway / smart contracts.
    When a live network is offline or unconfigured, safely surfaces UNAVAILABLE status
    without fabricating bogus blockchain transaction receipts.
    """

    def __init__(
        self,
        channel: str = "ecotrace-channel",
        chaincode: str = "ecotrace-lifecycle",
        network: str = "ecotrace-channel",
        provider: str = "hyperledger_fabric",
        gateway_client: Any | None = None,
    ) -> None:
        self._channel = channel
        self._chaincode = chaincode
        self._network = network
        self._provider = provider
        self._client = gateway_client

    def is_available(self) -> bool:
        """Return True if gateway client is actively connected."""
        return self._client is not None

    def anchor(self, anchor: ExternalTrustAnchor, overwrite: bool = False) -> ExternalTrustAnchor:
        """Submit anchor transaction to Hyperledger Fabric."""
        if self._client is None:
            logger.bind(device_id=anchor.device_id).warning(
                "Cannot submit anchor: Hyperledger Fabric gateway is offline or not connected."
            )
            raise ExternalLedgerUnavailableError(
                "Hyperledger Fabric external ledger is currently unavailable (not connected to live network).",
                details={"provider": self._provider, "network": self._network, "channel": self._channel},
            )

        # Gateway invocation when live client is present
        try:
            tx_id = self._client.submitTransaction(
                "AnchorDevicePassport",
                anchor.device_id,
                anchor.passport_fingerprint,
                anchor.algorithm,
            )
            return ExternalTrustAnchor(
                external_anchor_id=anchor.external_anchor_id,
                device_id=anchor.device_id,
                passport_fingerprint=anchor.passport_fingerprint,
                algorithm=anchor.algorithm,
                provider=self._provider,
                network=self._network,
                transaction_id=str(tx_id),
                anchored_at=_utc_now().isoformat(),
                status="ANCHORED",
                metadata=anchor.metadata,
            )
        except ExternalLedgerError:
            # Already a correctly classified domain error (e.g. a P6.2
            # FabricGatewayClient FabricTransactionError/FabricUnavailable) —
            # propagate it as-is rather than flattening it to UNAVAILABLE.
            raise
        except Exception as exc:
            logger.bind(device_id=anchor.device_id, error=str(exc)).error("Fabric transaction submission failed.")
            raise ExternalLedgerUnavailableError(f"Fabric transaction failed: {exc}") from exc

    def get_anchor(self, device_id: str) -> ExternalTrustAnchor | None:
        """Query anchor from Hyperledger Fabric ledger.

        Calls the P6.1 chaincode's ``GetDeviceAnchor`` query (via
        ``evaluateTransaction``) and parses its JSON ``PassportAnchor``
        response (``{deviceId, passportFingerprint, algorithm, anchoredAt,
        transactionId}``, or the literal string ``"null"`` when nothing is
        anchored) into the domain :class:`ExternalTrustAnchor`. The chaincode
        has no concept of a backend-side anchor id, so one is derived
        deterministically from the device id (stable across repeated queries;
        no randomness in a read-only path).

        Raises:
            ExternalLedgerError: A connectivity-class failure classified by
                the injected client (e.g. the P6.2 ``FabricGatewayClient``
                raising ``FabricUnavailable`` / ``FabricConnectionError``,
                both ``ExternalLedgerError`` subclasses) propagates rather
                than being swallowed into ``None`` — "the chain is
                unreachable" and "this device was never anchored" are
                different facts, and :meth:`verify_anchor` (the only in-tree
                caller that needs to tell them apart) distinguishes them via
                this exception. A generic, non-domain exception from an
                unrecognized duck-typed client — or a malformed-but-reachable
                response — still degrades to ``None`` (logged), matching the
                pre-P6.2 defensive behavior for callers this class was not
                specifically built to classify.
        """
        if self._client is None:
            return None

        try:
            raw = self._client.evaluateTransaction("GetDeviceAnchor", device_id)
        except ExternalLedgerError:
            raise
        except Exception as exc:
            logger.bind(device_id=device_id, error=str(exc)).warning("Fabric query evaluation failed.")
            return None

        if not raw or raw == "null":
            return None

        try:
            data = json.loads(raw)
        except (TypeError, ValueError) as exc:
            logger.bind(device_id=device_id, error=str(exc)).warning("Malformed GetDeviceAnchor payload from chaincode.")
            return None
        if not isinstance(data, dict):
            return None

        try:
            return ExternalTrustAnchor(
                external_anchor_id=f"chain-anc-{data['deviceId']}",
                device_id=data["deviceId"],
                passport_fingerprint=data["passportFingerprint"],
                algorithm=data.get("algorithm", "sha256"),
                provider=self._provider,
                network=self._network,
                transaction_id=data["transactionId"],
                anchored_at=data["anchoredAt"],
                status="ANCHORED",
                metadata={},
            )
        except KeyError as exc:
            logger.bind(device_id=device_id, error=str(exc)).warning(
                "GetDeviceAnchor payload missing an expected field."
            )
            return None

    def verify_anchor(
        self,
        device_id: str,
        current_fingerprint: str,
        algorithm: str = "sha256",
    ) -> ExternalTrustVerificationResult:
        """Verify fingerprint on Hyperledger Fabric ledger.

        Mirrors :meth:`InMemoryExternalTrustLedger.verify_anchor`'s
        NOT_ANCHORED / VERIFIED / MISMATCH semantics, backed by a real
        ``GetDeviceAnchor`` chaincode query instead of an in-memory dict.
        """
        eval_time = _utc_now().isoformat()

        if self._client is None:
            return ExternalTrustVerificationResult(
                device_id=device_id,
                status=ExternalTrustStatus.UNAVAILABLE,
                stored_fingerprint=None,
                current_fingerprint=current_fingerprint,
                algorithm=algorithm,
                provider=self._provider,
                network=self._network,
                transaction_id=None,
                anchored_at=None,
                verified_at=eval_time,
                message="Hyperledger Fabric external ledger is not connected to a live peer.",
                details={"provider": self._provider, "network": self._network, "connected": False},
            )

        try:
            stored = self.get_anchor(device_id)
        except ExternalLedgerError as exc:
            # A classified connectivity-class failure (e.g. FabricUnavailable /
            # FabricConnectionError from the P6.2 gateway client): the chain
            # could not be reached, which is a different fact from "this
            # device was never anchored" — never conflate the two.
            logger.bind(device_id=device_id, error=str(exc)).warning("Fabric ledger unreachable during verification.")
            return ExternalTrustVerificationResult(
                device_id=device_id,
                status=ExternalTrustStatus.UNAVAILABLE,
                stored_fingerprint=None,
                current_fingerprint=current_fingerprint,
                algorithm=algorithm,
                provider=self._provider,
                network=self._network,
                transaction_id=None,
                anchored_at=None,
                verified_at=eval_time,
                message=f"Hyperledger Fabric external ledger is unreachable: {exc.message}",
                details={"provider": self._provider, "network": self._network, "connected": True},
            )
        except Exception as exc:
            logger.bind(device_id=device_id, error=str(exc)).error("Fabric query evaluation failed unexpectedly.")
            return ExternalTrustVerificationResult(
                device_id=device_id,
                status=ExternalTrustStatus.ERROR,
                stored_fingerprint=None,
                current_fingerprint=current_fingerprint,
                algorithm=algorithm,
                provider=self._provider,
                network=self._network,
                transaction_id=None,
                anchored_at=None,
                verified_at=eval_time,
                message=f"Unexpected error querying Hyperledger Fabric ledger: {exc}",
                details={"provider": self._provider, "network": self._network},
            )

        if stored is None:
            return ExternalTrustVerificationResult(
                device_id=device_id,
                status=ExternalTrustStatus.NOT_ANCHORED,
                stored_fingerprint=None,
                current_fingerprint=current_fingerprint,
                algorithm=algorithm,
                provider=self._provider,
                network=self._network,
                transaction_id=None,
                anchored_at=None,
                verified_at=eval_time,
                message=f"Device '{device_id}' has not been anchored on external ledger '{self._network}'.",
                details={"provider": self._provider, "network": self._network},
            )

        if stored.passport_fingerprint == current_fingerprint and stored.algorithm == algorithm:
            return ExternalTrustVerificationResult(
                device_id=device_id,
                status=ExternalTrustStatus.VERIFIED,
                stored_fingerprint=stored.passport_fingerprint,
                current_fingerprint=current_fingerprint,
                algorithm=algorithm,
                provider=self._provider,
                network=self._network,
                transaction_id=stored.transaction_id,
                anchored_at=stored.anchored_at,
                verified_at=eval_time,
                message="External ledger anchor verified: fingerprint and algorithm match recorded state.",
                details={"external_anchor_id": stored.external_anchor_id, "metadata": stored.metadata},
            )

        return ExternalTrustVerificationResult(
            device_id=device_id,
            status=ExternalTrustStatus.MISMATCH,
            stored_fingerprint=stored.passport_fingerprint,
            current_fingerprint=current_fingerprint,
            algorithm=algorithm,
            provider=self._provider,
            network=self._network,
            transaction_id=stored.transaction_id,
            anchored_at=stored.anchored_at,
            verified_at=eval_time,
            message="External ledger fingerprint MISMATCH: recorded on-chain state differs from current passport.",
            details={
                "external_anchor_id": stored.external_anchor_id,
                "stored_fingerprint": stored.passport_fingerprint,
                "current_fingerprint": current_fingerprint,
            },
        )
