"""Tests for the optional fingerprint identity seam (milestone M1.6).

The fingerprint engine can optionally consume an :class:`OCRIdentity` without
breaking M1.5 backward compatibility: the ``identity`` key is emitted only when
at least one OCR field is present, so fingerprints generated without OCR remain
byte-identical to before.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from device_ai.fingerprint.models import DeviceFingerprint
from device_ai.fingerprint.repository import InMemoryFingerprintRepository
from device_ai.fingerprint.service import FingerprintService
from device_ai.fingerprint.verification import VerificationEngine
from device_ai.inference.ecoid import EcoIDGenerator
from device_ai.inference.predictor import MockEmbeddingEncoder
from device_ai.ocr.models import OCRIdentity
from device_ai.preprocessing.image_loader import LoadedImage, load_image

from .conftest import make_image_bytes

_FIXED_CLOCK: Callable[[], datetime] = lambda: datetime(  # noqa: E731
    2026, 8, 1, 12, 0, 0, tzinfo=UTC
)


def _load(color: tuple[int, int, int] = (10, 20, 30)) -> LoadedImage:
    """Return a decoded LoadedImage for identity-seam tests."""
    return load_image(
        make_image_bytes(color=color),
        filename="device.png",
        content_type="image/png",
    )


def _service() -> FingerprintService:
    """Build a service wired to the mock encoder and an in-memory store."""
    return FingerprintService(
        encoder=MockEmbeddingEncoder(),
        repository=InMemoryFingerprintRepository(),
        ecoid_generator=EcoIDGenerator(year=2026),
        verifier=VerificationEngine(threshold=0.85, metric="cosine"),
        clock=_FIXED_CLOCK,
    )


class TestGenerateWithoutIdentity:
    """Backward compatibility: no identity → empty, omitted on serialization."""

    def test_identity_defaults_empty(self) -> None:
        fingerprint = _service().generate([_load()])
        assert fingerprint.identity == {}

    def test_to_dict_omits_identity_key_when_empty(self) -> None:
        fingerprint = _service().generate([_load()])
        assert "identity" not in fingerprint.to_dict()


class TestGenerateWithIdentity:
    """Supplying an OCRIdentity attaches only its non-empty fields."""

    def test_non_empty_fields_attached(self) -> None:
        identity = OCRIdentity(manufacturer="Dell", imei="490154203237518")
        fingerprint = _service().generate([_load()], identity=identity)
        assert fingerprint.identity == {
            "manufacturer": "Dell",
            "imei": "490154203237518",
        }

    def test_to_dict_includes_identity_when_present(self) -> None:
        identity = OCRIdentity(manufacturer="Dell")
        fingerprint = _service().generate([_load()], identity=identity)
        payload = fingerprint.to_dict()
        assert payload["identity"] == {"manufacturer": "Dell"}

    def test_empty_identity_object_stays_omitted(self) -> None:
        fingerprint = _service().generate([_load()], identity=OCRIdentity())
        assert fingerprint.identity == {}
        assert "identity" not in fingerprint.to_dict()


class TestRoundTrip:
    """to_dict/from_dict is stable with and without identity."""

    def test_round_trip_with_identity(self) -> None:
        identity = OCRIdentity(manufacturer="Dell", serial_number="ABC12345")
        fingerprint = _service().generate([_load()], identity=identity)
        restored = DeviceFingerprint.from_dict(fingerprint.to_dict())
        assert restored == fingerprint

    def test_round_trip_without_identity(self) -> None:
        fingerprint = _service().generate([_load()])
        restored = DeviceFingerprint.from_dict(fingerprint.to_dict())
        assert restored == fingerprint
        assert restored.identity == {}
