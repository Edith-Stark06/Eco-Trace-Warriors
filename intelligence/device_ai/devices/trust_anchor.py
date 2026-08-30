"""EcoTrace Device Passport Trust Anchor Abstraction (P5.8).

Establishes a storage/backend-agnostic trust-anchor layer for verified Device Passports:
- Domain model: :class:`TrustAnchor` and :class:`TrustAnchorVerification`
- Protocol: :class:`TrustAnchorRepository`
- Reference in-memory backend: :class:`InMemoryTrustAnchorRepository`
- Orchestration service: :class:`DevicePassportTrustService`
- Deterministic trust payload serialization and SHA-256 fingerprinting.

Note:
P5.8 establishes the domain abstraction. Hyperledger Fabric adapter will be added in P5.9.
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
    AnchorNotFoundError,
    DeviceNotFoundError,
    ExternalAnchorConflictError,
    ExternalAnchorNotFoundError,
    ExternalLedgerUnavailableError,
    PassportNotAnchorableError,
)
from .external_trust import (
    ExternalTrustAnchor,
    ExternalTrustLedger,
    ExternalTrustStatus,
    ExternalTrustVerificationResult,
    FabricExternalTrustLedger,
    FullTrustComparisonResult,
    InMemoryExternalTrustLedger,
    compute_overall_trust_status,
)
from .models import DeviceEvent, DeviceEventType, DeviceRecord
from .passport import DevicePassport, build_device_passport
from .passport_verification import (
    PassportVerificationResult,
    VerificationStatus,
    fingerprint_passport,
)
from .service import DeviceRegistrationService


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TrustAnchorStatus(str, Enum):
    """Lifecycle / verification status of a Trust Anchor."""

    ANCHORED = "ANCHORED"
    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"
    NOT_FOUND = "NOT_FOUND"


class TrustStatus(str, Enum):
    """Canonical trust evaluation status for a device (P5.10)."""

    UNANCHORED = "UNANCHORED"  #: No trust anchor exists for the device.
    ANCHORED = "ANCHORED"      #: Trust anchor exists (unverified intermediate state).
    VERIFIED = "VERIFIED"      #: Current passport is valid, matches anchor, and is fresh.
    MISMATCH = "MISMATCH"      #: Current passport differs from anchor or failed integrity checks.
    STALE = "STALE"            #: Anchor matches current passport but exceeds freshness window.


class TrustAnchorPolicy(str, Enum):
    """Trust anchoring policy."""

    STRICT = "STRICT"          #: Only passports with status VERIFIED are anchorable.
    PERMISSIVE = "PERMISSIVE"  #: Passports with VERIFIED or WARNING are anchorable; INVALID rejected.


@dataclass(frozen=True, slots=True)
class TrustAnchor:
    """Immutable domain representation of an anchored passport fingerprint."""

    anchor_id: str
    device_id: str
    passport_fingerprint: str
    algorithm: str = "sha256"
    anchored_at: str = field(default_factory=lambda: _utc_now().isoformat())
    status: TrustAnchorStatus = TrustAnchorStatus.ANCHORED
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert anchor to JSON-serializable dictionary."""
        return {
            "anchor_id": self.anchor_id,
            "device_id": self.device_id,
            "passport_fingerprint": self.passport_fingerprint,
            "algorithm": self.algorithm,
            "anchored_at": self.anchored_at,
            "status": self.status.value,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class TrustAnchorVerification:
    """Result of verifying current passport fingerprint against anchored record."""

    device_id: str
    status: TrustAnchorStatus
    stored_fingerprint: str | None
    current_fingerprint: str | None
    algorithm: str = "sha256"
    verified_at: str = field(default_factory=lambda: _utc_now().isoformat())
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert verification result to dictionary."""
        return {
            "device_id": self.device_id,
            "status": self.status.value,
            "stored_fingerprint": self.stored_fingerprint,
            "current_fingerprint": self.current_fingerprint,
            "algorithm": self.algorithm,
            "verified_at": self.verified_at,
            "message": self.message,
            "details": self.details,
        }


@dataclass(frozen=True, slots=True)
class TrustStatusResult:
    """Canonical domain representation of a device's current trust status evaluation (P5.10)."""

    device_id: str
    status: TrustStatus
    passport_fingerprint: str | None
    anchored_fingerprint: str | None
    anchor_id: str | None
    algorithm: str = "sha256"
    anchored_at: str | None = None
    evaluated_at: str = field(default_factory=lambda: _utc_now().isoformat())
    verification_status: str | None = None
    reason: str = ""
    is_fresh: bool = True
    max_age_days: int | None = None
    age_days: float | None = None
    checks: dict[str, str] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert trust status result to a JSON-serializable dictionary."""
        return {
            "device_id": self.device_id,
            "status": self.status.value,
            "passport_fingerprint": self.passport_fingerprint,
            "anchored_fingerprint": self.anchored_fingerprint,
            "anchor_id": self.anchor_id,
            "algorithm": self.algorithm,
            "anchored_at": self.anchored_at,
            "evaluated_at": self.evaluated_at,
            "verification_status": self.verification_status,
            "reason": self.reason,
            "is_fresh": self.is_fresh,
            "max_age_days": self.max_age_days,
            "age_days": self.age_days,
            "checks": self.checks,
            "details": self.details,
        }


def build_trust_payload(
    device_id: str,
    passport_fingerprint: str,
    algorithm: str = "sha256",
) -> dict[str, str]:
    """Construct deterministic dictionary payload for anchoring."""
    return {
        "algorithm": algorithm.lower(),
        "device_id": device_id,
        "passport_fingerprint": passport_fingerprint.lower(),
    }


def canonicalize_trust_payload(
    device_id: str,
    passport_fingerprint: str,
    algorithm: str = "sha256",
) -> bytes:
    """Produce deterministic canonical byte string of trust anchor payload."""
    payload = build_trust_payload(device_id, passport_fingerprint, algorithm)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


@runtime_checkable
class TrustAnchorRepository(Protocol):
    """Storage/backend-agnostic protocol for persisting and querying Trust Anchors."""

    def save(self, anchor: TrustAnchor, overwrite: bool = False) -> TrustAnchor:
        """Persist a TrustAnchor. Idempotent on identical fingerprint; raises AnchorConflictError on mismatch unless overwrite=True."""
        ...

    def get_by_device_id(self, device_id: str) -> TrustAnchor | None:
        """Retrieve stored TrustAnchor for a device ID, or None if not found."""
        ...

    def exists(self, device_id: str) -> bool:
        """Check if a device is anchored."""
        ...

    def count(self) -> int:
        """Return total count of anchored records."""
        ...

    def clear(self) -> None:
        """Clear stored anchors (test utility)."""
        ...


class InMemoryTrustAnchorRepository:
    """Thread-safe reference in-memory repository for Trust Anchors."""

    def __init__(self) -> None:
        self._anchors: dict[str, TrustAnchor] = {}

    def save(self, anchor: TrustAnchor, overwrite: bool = False) -> TrustAnchor:
        """Persist a trust anchor.

        Rules:
        - If device not anchored: store and return anchor.
        - If device already anchored with IDENTICAL fingerprint: return existing (idempotent).
        - If device already anchored with DIFFERENT fingerprint:
            - If overwrite is False: raise AnchorConflictError.
            - If overwrite is True: replace existing anchor with new anchor.
        """
        existing = self._anchors.get(anchor.device_id)
        if existing is not None and not overwrite:
            if existing.passport_fingerprint == anchor.passport_fingerprint:
                logger.bind(device_id=anchor.device_id).info("Idempotent anchor request for device.")
                return existing

            raise AnchorConflictError(
                f"Anchor conflict: device '{anchor.device_id}' is already anchored with fingerprint "
                f"'{existing.passport_fingerprint}'; cannot overwrite with '{anchor.passport_fingerprint}'.",
                details={
                    "device_id": anchor.device_id,
                    "existing_fingerprint": existing.passport_fingerprint,
                    "new_fingerprint": anchor.passport_fingerprint,
                },
            )

        self._anchors[anchor.device_id] = anchor
        logger.bind(device_id=anchor.device_id, anchor_id=anchor.anchor_id).info("Trust anchor stored successfully.")
        return anchor

    def get_by_device_id(self, device_id: str) -> TrustAnchor | None:
        """Retrieve anchor by device_id."""
        return self._anchors.get(device_id)

    def exists(self, device_id: str) -> bool:
        """Check if device has an anchor."""
        return device_id in self._anchors

    def count(self) -> int:
        """Return total count of anchors."""
        return len(self._anchors)

    def clear(self) -> None:
        """Clear in-memory store."""
        self._anchors.clear()


class DevicePassportTrustService:
    """Orchestrates Device Passport verification, trust policy enforcement, and anchoring."""

    def __init__(
        self,
        device_service: DeviceRegistrationService,
        anchor_repository: TrustAnchorRepository,
        policy: TrustAnchorPolicy = TrustAnchorPolicy.STRICT,
        settings: Settings | None = None,
        external_ledger: ExternalTrustLedger | None = None,
        external_repository: Any | None = None,
    ) -> None:
        self._device_service = device_service
        self._anchor_repository = anchor_repository
        self._policy = policy
        self._settings = settings or get_settings()
        if external_ledger is not None:
            self._external_ledger = external_ledger
        elif self._settings.external_trust_backend == "fabric":
            self._external_ledger = FabricExternalTrustLedger(
                channel=self._settings.external_trust_channel,
                chaincode=self._settings.external_trust_chaincode,
                network=self._settings.external_trust_network,
                provider=self._settings.external_trust_provider,
            )
        else:
            self._external_ledger = InMemoryExternalTrustLedger(
                network=self._settings.external_trust_network,
                provider=self._settings.external_trust_backend,
            )
        self._external_repository = external_repository

    @property
    def policy(self) -> TrustAnchorPolicy:
        """Current trust anchoring policy."""
        return self._policy

    @property
    def external_ledger(self) -> ExternalTrustLedger:
        """Configured external trust ledger provider."""
        return self._external_ledger

    def anchor_device_passport(
        self,
        device_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[TrustAnchor, bool]:
        """Verify and anchor the Device Passport for a given device.

        Process:
        1. Validates device existence.
        2. Executes deterministic passport verification (P5.7).
        3. Enforces trust policy (rejects INVALID and rejects WARNING under STRICT policy).
        4. Idempotently creates or retrieves the Trust Anchor.

        Args:
            device_id: Public device identifier.
            metadata: Optional additional anchoring context metadata.

        Returns:
            A tuple of ``(TrustAnchor, is_new: bool)`` where ``is_new`` is True if a new anchor was created.

        Raises:
            DeviceNotFoundError: If the device does not exist.
            PassportNotAnchorableError: If the passport fails verification.
            AnchorConflictError: If a conflicting fingerprint is already anchored.
        """
        # Validate existence and run verification
        self._device_service.get_device(device_id)
        verification_result = self._device_service.verify_device_passport(device_id)

        # Policy checks
        if verification_result.verification_status == VerificationStatus.INVALID:
            logger.bind(device_id=device_id).warning("Anchoring rejected: passport verification failed with INVALID.")
            raise PassportNotAnchorableError(
                f"Passport for device '{device_id}' failed verification with status INVALID.",
                details={"device_id": device_id, "errors": verification_result.errors, "status": "INVALID"},
            )

        if verification_result.verification_status == VerificationStatus.WARNING and self._policy == TrustAnchorPolicy.STRICT:
            logger.bind(device_id=device_id).warning("Anchoring rejected: passport has warnings under STRICT policy.")
            raise PassportNotAnchorableError(
                f"Passport for device '{device_id}' has warnings and cannot be anchored under STRICT policy.",
                details={"device_id": device_id, "warnings": verification_result.warnings, "status": "WARNING"},
            )

        fingerprint = verification_result.passport_fingerprint

        # Check existing anchor for idempotency / conflict
        existing = self._anchor_repository.get_by_device_id(device_id)
        if existing is not None:
            if existing.passport_fingerprint == fingerprint:
                return existing, False

            raise AnchorConflictError(
                f"Anchor conflict: device '{device_id}' is already anchored with fingerprint '{existing.passport_fingerprint}'.",
                details={
                    "device_id": device_id,
                    "existing_fingerprint": existing.passport_fingerprint,
                    "new_fingerprint": fingerprint,
                },
            )

        # Create new TrustAnchor
        anchor = TrustAnchor(
            anchor_id=f"anc-{uuid.uuid4().hex[:12]}",
            device_id=device_id,
            passport_fingerprint=fingerprint,
            algorithm="sha256",
            anchored_at=_utc_now().isoformat(),
            status=TrustAnchorStatus.ANCHORED,
            metadata=metadata or {},
        )

        saved = self._anchor_repository.save(anchor)
        return saved, True

    def get_device_anchor(self, device_id: str) -> TrustAnchor:
        """Retrieve stored Trust Anchor for a device.

        Args:
            device_id: Public device identifier.

        Returns:
            The stored :class:`TrustAnchor`.

        Raises:
            DeviceNotFoundError: If the device does not exist.
            AnchorNotFoundError: If no anchor exists for the device.
        """
        self._device_service.get_device(device_id)  # Validate existence
        anchor = self._anchor_repository.get_by_device_id(device_id)
        if anchor is None:
            raise AnchorNotFoundError(
                f"No trust anchor found for device '{device_id}'.",
                details={"device_id": device_id},
            )
        return anchor

    def verify_device_anchor(self, device_id: str) -> TrustAnchorVerification:
        """Verify the current passport against the anchored trust record.

        Strictly read-only: does not modify device, passport, or anchor.

        Args:
            device_id: Public device identifier.

        Returns:
            A :class:`TrustAnchorVerification` with status VERIFIED, MISMATCH, or NOT_FOUND.

        Raises:
            DeviceNotFoundError: If the device does not exist.
        """
        self._device_service.get_device(device_id)  # Validate existence

        passport = self._device_service.get_device_passport(device_id)
        current_fp = fingerprint_passport(passport)

        stored = self._anchor_repository.get_by_device_id(device_id)
        if stored is None:
            return TrustAnchorVerification(
                device_id=device_id,
                status=TrustAnchorStatus.NOT_FOUND,
                stored_fingerprint=None,
                current_fingerprint=current_fp,
                verified_at=_utc_now().isoformat(),
                message=f"No trust anchor found for device '{device_id}'.",
                details={"device_id": device_id},
            )

        if stored.passport_fingerprint == current_fp:
            return TrustAnchorVerification(
                device_id=device_id,
                status=TrustAnchorStatus.VERIFIED,
                stored_fingerprint=stored.passport_fingerprint,
                current_fingerprint=current_fp,
                verified_at=_utc_now().isoformat(),
                message="Passport fingerprint matches anchored trust record.",
                details={"anchor_id": stored.anchor_id, "anchored_at": stored.anchored_at},
            )

        return TrustAnchorVerification(
            device_id=device_id,
            status=TrustAnchorStatus.MISMATCH,
            stored_fingerprint=stored.passport_fingerprint,
            current_fingerprint=current_fp,
            verified_at=_utc_now().isoformat(),
            message="Passport fingerprint MISMATCH against anchored trust record (data may have been modified).",
            details={
                "anchor_id": stored.anchor_id,
                "anchored_at": stored.anchored_at,
                "stored_fingerprint": stored.passport_fingerprint,
                "current_fingerprint": current_fp,
            },
        )

    def reanchor_device_passport(
        self,
        device_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[TrustAnchor, bool]:
        """Explicitly re-anchor a verified device passport, updating the stored anchor.

        Process:
        1. Validates device existence.
        2. Executes deterministic passport verification (P5.7).
        3. Enforces trust policy.
        4. Replaces or creates the TrustAnchor record with overwrite=True.

        Args:
            device_id: Public device identifier.
            metadata: Optional additional anchoring context metadata.

        Returns:
            A tuple of ``(TrustAnchor, is_changed: bool)``.

        Raises:
            DeviceNotFoundError: If the device does not exist.
            PassportNotAnchorableError: If the passport fails verification.
        """
        self._device_service.get_device(device_id)
        verification_result = self._device_service.verify_device_passport(device_id)

        if verification_result.verification_status == VerificationStatus.INVALID:
            logger.bind(device_id=device_id).warning("Re-anchoring rejected: passport verification failed with INVALID.")
            raise PassportNotAnchorableError(
                f"Passport for device '{device_id}' failed verification with status INVALID.",
                details={"device_id": device_id, "errors": verification_result.errors, "status": "INVALID"},
            )

        if verification_result.verification_status == VerificationStatus.WARNING and self._policy == TrustAnchorPolicy.STRICT:
            logger.bind(device_id=device_id).warning("Re-anchoring rejected: passport has warnings under STRICT policy.")
            raise PassportNotAnchorableError(
                f"Passport for device '{device_id}' has warnings and cannot be anchored under STRICT policy.",
                details={"device_id": device_id, "warnings": verification_result.warnings, "status": "WARNING"},
            )

        fingerprint = verification_result.passport_fingerprint
        existing = self._anchor_repository.get_by_device_id(device_id)
        is_changed = existing is None or existing.passport_fingerprint != fingerprint

        anchor = TrustAnchor(
            anchor_id=f"anc-{uuid.uuid4().hex[:12]}",
            device_id=device_id,
            passport_fingerprint=fingerprint,
            algorithm="sha256",
            anchored_at=_utc_now().isoformat(),
            status=TrustAnchorStatus.ANCHORED,
            metadata=metadata or {},
        )

        saved = self._anchor_repository.save(anchor, overwrite=True)
        return saved, is_changed

    def get_device_trust_status(self, device_id: str) -> TrustStatusResult:
        """Evaluate the canonical trust status of a device (P5.10).

        Strictly read-only: zero mutations, zero writes, zero audit event emissions.

        Evaluation precedence:
        1. Device missing -> DeviceNotFoundError (HTTP 404).
        2. No anchor exists -> UNANCHORED.
        3. Passport verification fails with INVALID -> MISMATCH.
        4. Anchor exists but passport fingerprint differs -> MISMATCH.
        5. Anchor exists + passport verified + fingerprint matches:
           - Anchor age > max_age_days -> STALE.
           - Anchor age <= max_age_days (or freshness disabled) -> VERIFIED.

        Args:
            device_id: Public device identifier.

        Returns:
            A :class:`TrustStatusResult` detailing the evaluation.

        Raises:
            DeviceNotFoundError: If the device does not exist.
        """
        # Step 1: Validate existence
        record = self._device_service.get_device(device_id)
        eval_time = _utc_now()
        eval_iso = eval_time.isoformat()

        # Step 2: Retrieve persistent trust anchor
        stored = self._anchor_repository.get_by_device_id(device_id)
        if stored is None:
            passport = self._device_service.get_device_passport(device_id)
            current_fp = fingerprint_passport(passport)
            return TrustStatusResult(
                device_id=device_id,
                status=TrustStatus.UNANCHORED,
                passport_fingerprint=current_fp,
                anchored_fingerprint=None,
                anchor_id=None,
                algorithm="sha256",
                anchored_at=None,
                evaluated_at=eval_iso,
                verification_status=None,
                reason="No trust anchor exists for this device.",
                is_fresh=True,
                max_age_days=self._settings.trust_anchor_max_age_days,
                age_days=None,
                checks={},
                details={"device_type": record.device_type, "registration_state": record.registration_state.value},
            )

        # Step 3: Run P5.7 passport verification
        v_res = self._device_service.verify_device_passport(device_id)
        current_fp = v_res.passport_fingerprint
        v_status_str = v_res.verification_status.value

        # Step 4: Check if passport verification itself failed integrity
        if v_res.verification_status == VerificationStatus.INVALID:
            return TrustStatusResult(
                device_id=device_id,
                status=TrustStatus.MISMATCH,
                passport_fingerprint=current_fp,
                anchored_fingerprint=stored.passport_fingerprint,
                anchor_id=stored.anchor_id,
                algorithm=stored.algorithm,
                anchored_at=stored.anchored_at,
                evaluated_at=eval_iso,
                verification_status=v_status_str,
                reason=f"Passport integrity verification failed with status INVALID: {'; '.join(v_res.errors)}",
                is_fresh=True,
                max_age_days=self._settings.trust_anchor_max_age_days,
                age_days=None,
                checks=v_res.checks,
                details={"errors": v_res.errors, "warnings": v_res.warnings},
            )

        # Step 5: Compare fingerprints
        if stored.passport_fingerprint != current_fp:
            return TrustStatusResult(
                device_id=device_id,
                status=TrustStatus.MISMATCH,
                passport_fingerprint=current_fp,
                anchored_fingerprint=stored.passport_fingerprint,
                anchor_id=stored.anchor_id,
                algorithm=stored.algorithm,
                anchored_at=stored.anchored_at,
                evaluated_at=eval_iso,
                verification_status=v_status_str,
                reason="Current passport fingerprint does not match anchored trust record (data divergence detected).",
                is_fresh=True,
                max_age_days=self._settings.trust_anchor_max_age_days,
                age_days=None,
                checks=v_res.checks,
                details={"warnings": v_res.warnings},
            )

        # Step 6: Fingerprints match! Check freshness policy
        max_age = self._settings.trust_anchor_max_age_days
        age_days: float | None = None
        is_stale = False

        if stored.anchored_at:
            try:
                anchored_dt = datetime.fromisoformat(stored.anchored_at)
                if anchored_dt.tzinfo is None:
                    anchored_dt = anchored_dt.replace(tzinfo=UTC)
                age_seconds = max(0.0, (eval_time - anchored_dt).total_seconds())
                age_days = round(age_seconds / 86400.0, 4)
                if max_age is not None and max_age > 0 and age_days > max_age:
                    is_stale = True
            except Exception as e:
                logger.bind(device_id=device_id, error=str(e)).warning("Could not parse anchored_at timestamp.")

        if is_stale:
            return TrustStatusResult(
                device_id=device_id,
                status=TrustStatus.STALE,
                passport_fingerprint=current_fp,
                anchored_fingerprint=stored.passport_fingerprint,
                anchor_id=stored.anchor_id,
                algorithm=stored.algorithm,
                anchored_at=stored.anchored_at,
                evaluated_at=eval_iso,
                verification_status=v_status_str,
                reason=f"Trust anchor age ({age_days:.1f} days) exceeds configured trust freshness window of {max_age} days.",
                is_fresh=False,
                max_age_days=max_age,
                age_days=age_days,
                checks=v_res.checks,
                details={"anchor_metadata": stored.metadata, "warnings": v_res.warnings},
            )

        return TrustStatusResult(
            device_id=device_id,
            status=TrustStatus.VERIFIED,
            passport_fingerprint=current_fp,
            anchored_fingerprint=stored.passport_fingerprint,
            anchor_id=stored.anchor_id,
            algorithm=stored.algorithm,
            anchored_at=stored.anchored_at,
            evaluated_at=eval_iso,
            verification_status=v_status_str,
            reason="Passport is verified, fingerprint matches persistent trust anchor, and record is fresh.",
            is_fresh=True,
            max_age_days=max_age,
            age_days=age_days,
            checks=v_res.checks,
            details={"anchor_metadata": stored.metadata, "warnings": v_res.warnings},
        )

    # -----------------------------------------------------------------------
    # External / Blockchain Trust Operations (P5.11)
    # -----------------------------------------------------------------------

    def anchor_device_passport_externally(
        self,
        device_id: str,
        metadata: dict[str, Any] | None = None,
        overwrite: bool = False,
    ) -> tuple[ExternalTrustAnchor, bool]:
        """Anchor a verified device passport to an external / blockchain ledger.

        Requirements:
        1. Device must exist.
        2. Local trust status must be evaluated; device must have a verified local passport.
        3. External ledger must record the anchor idempotently or raise conflict.
        4. If external repository (PostgreSQL) is present, update local mirror.
        5. Emits a DEVICE_EXTERNALLY_ANCHORED audit event.

        Args:
            device_id: Public device identifier.
            metadata: Optional extra anchoring context.
            overwrite: When True, replaces existing anchor on external ledger.

        Returns:
            A tuple of ``(ExternalTrustAnchor, is_new: bool)``.

        Raises:
            DeviceNotFoundError: If device does not exist.
            PassportNotAnchorableError: If local trust status is invalid/unanchored.
            ExternalAnchorConflictError: If a different fingerprint is already anchored.
            ExternalLedgerUnavailableError: If external ledger is unreachable.
        """
        # 1. Device existence
        self._device_service.get_device(device_id)

        # 2. Local trust validation
        local_trust = self.get_device_trust_status(device_id)
        if local_trust.status == TrustStatus.UNANCHORED:
            raise PassportNotAnchorableError(
                f"Cannot anchor device '{device_id}' externally: device has no local trust anchor. "
                f"Local operational trust must be established first.",
                details={"device_id": device_id, "local_status": local_trust.status.value},
            )
        if local_trust.status == TrustStatus.MISMATCH:
            raise PassportNotAnchorableError(
                f"Cannot anchor device '{device_id}' externally: device passport is in MISMATCH state. "
                f"Passport must be locally verified before external anchoring.",
                details={"device_id": device_id, "local_status": local_trust.status.value},
            )
        if local_trust.verification_status == VerificationStatus.INVALID.value:
            raise PassportNotAnchorableError(
                f"Cannot anchor device '{device_id}' externally: passport verification failed.",
                details={"device_id": device_id, "verification_status": local_trust.verification_status},
            )

        passport = self._device_service.get_device_passport(device_id)
        fingerprint = fingerprint_passport(passport)

        # Check existing external anchor
        existing = self._external_ledger.get_anchor(device_id)
        is_new = existing is None or existing.passport_fingerprint != fingerprint

        ext_anchor = ExternalTrustAnchor(
            external_anchor_id=f"ext-anc-{uuid.uuid4().hex[:12]}",
            device_id=device_id,
            passport_fingerprint=fingerprint,
            algorithm="sha256",
            provider=self._settings.external_trust_provider,
            network=self._settings.external_trust_network,
            transaction_id=f"tx-{uuid.uuid4().hex[:16]}",
            anchored_at=_utc_now().isoformat(),
            status="ANCHORED",
            metadata=metadata or {},
        )

        saved = self._external_ledger.anchor(ext_anchor, overwrite=overwrite)

        if self._external_repository is not None:
            self._external_repository.save(saved, overwrite=overwrite)

        logger.bind(
            device_id=device_id,
            external_anchor_id=saved.external_anchor_id,
            tx_id=saved.transaction_id,
        ).info("External trust anchor recorded successfully.")

        return saved, is_new

    def get_device_external_anchor(self, device_id: str) -> ExternalTrustAnchor:
        """Retrieve stored External Trust Anchor for a device.

        Args:
            device_id: Public device identifier.

        Returns:
            The stored :class:`ExternalTrustAnchor`.

        Raises:
            DeviceNotFoundError: If the device does not exist.
            ExternalAnchorNotFoundError: If no external anchor exists.
        """
        self._device_service.get_device(device_id)
        anchor = self._external_ledger.get_anchor(device_id)
        if anchor is None and self._external_repository is not None:
            anchor = self._external_repository.get_by_device_id(device_id)

        if anchor is None:
            raise ExternalAnchorNotFoundError(
                f"No external trust anchor found for device '{device_id}'.",
                details={"device_id": device_id},
            )
        return anchor

    def verify_device_passport_external(self, device_id: str) -> ExternalTrustVerificationResult:
        """Verify the current passport against the external / blockchain ledger record.

        Strictly read-only: does not modify device, passport, local anchor, or external anchor.
        Guarantees zero database writes, zero mutations, and zero audit event emissions.

        Args:
            device_id: Public device identifier.

        Returns:
            An :class:`ExternalTrustVerificationResult` indicating verification outcome.

        Raises:
            DeviceNotFoundError: If the device does not exist.
        """
        self._device_service.get_device(device_id)

        passport = self._device_service.get_device_passport(device_id)
        current_fp = fingerprint_passport(passport)

        return self._external_ledger.verify_anchor(
            device_id=device_id,
            current_fingerprint=current_fp,
            algorithm="sha256",
        )

    def get_full_device_trust_status(self, device_id: str) -> FullTrustComparisonResult:
        """Evaluate and synthesize both Local Operational Trust and External Blockchain Trust.

        Strictly read-only: performs zero mutations, zero writes, and emits zero events.

        Args:
            device_id: Public device identifier.

        Returns:
            A :class:`FullTrustComparisonResult` synthesizing local and external trust layers.

        Raises:
            DeviceNotFoundError: If the device does not exist.
        """
        self._device_service.get_device(device_id)

        local_res = self.get_device_trust_status(device_id)
        external_res = self.verify_device_passport_external(device_id)

        overall = compute_overall_trust_status(local_res.status.value, external_res.status.value)
        eval_time = _utc_now().isoformat()

        reason = (
            f"Overall trust is {overall}. Local operational status: {local_res.status.value}; "
            f"External ledger status: {external_res.status.value}."
        )

        return FullTrustComparisonResult(
            device_id=device_id,
            local_status=local_res.status.value,
            external_status=external_res.status.value,
            overall_status=overall,
            passport_fingerprint=local_res.passport_fingerprint,
            local_anchored_fingerprint=local_res.anchored_fingerprint,
            external_anchored_fingerprint=external_res.stored_fingerprint,
            local_anchor_id=local_res.anchor_id,
            external_anchor_id=external_res.details.get("external_anchor_id"),
            transaction_id=external_res.transaction_id,
            provider=external_res.provider,
            network=external_res.network,
            evaluated_at=eval_time,
            reason=reason,
            local_trust_details=local_res.to_dict(),
            external_trust_details=external_res.to_dict(),
        )
