"""Brand intelligence extractor and normalizer (P5.3).

Identifies canonical manufacturer / brand names from OCR text extractions.
Adheres strictly to the principles:
- Never infer brand solely from device class.
- Never fabricate brand names.
- Explicitly return UNKNOWN when no reliable brand signal is found.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from .enrichment_models import BrandAssessment

#: Canonical manufacturer mapping (lowercase search token -> Canonical display name)
CANONICAL_BRAND_MAP: dict[str, str] = {
    "dell": "Dell",
    "hp": "HP",
    "hewlett-packard": "HP",
    "hewlett packard": "HP",
    "apple": "Apple",
    "samsung": "Samsung",
    "lenovo": "Lenovo",
    "asus": "Asus",
    "acer": "Acer",
    "microsoft": "Microsoft",
    "sony": "Sony",
    "lg": "LG",
    "toshiba": "Toshiba",
    "google": "Google",
    "xiaomi": "Xiaomi",
    "huawei": "Huawei",
    "nokia": "Nokia",
    "motorola": "Motorola",
    "oneplus": "OnePlus",
    "canon": "Canon",
    "nikon": "Nikon",
    "epson": "Epson",
    "bose": "Bose",
    "sennheiser": "Sennheiser",
    "logitech": "Logitech",
    "razer": "Razer",
    "panasonic": "Panasonic",
    "philips": "Philips",
    "brother": "Brother",
    "fujifilm": "Fujifilm",
    "corsair": "Corsair",
    "steelseries": "SteelSeries",
}


@runtime_checkable
class BrandIntelligence(Protocol):
    """Protocol interface for brand extraction."""

    def assess_brand(
        self,
        ocr_text: str | None = None,
        confidence: float | None = None,
    ) -> BrandAssessment:
        """Assess brand from OCR text."""
        ...


class RuleBasedBrandIntelligence:
    """Deterministic brand extractor matching text tokens against canonical brands."""

    def __init__(self, brand_map: dict[str, str] | None = None) -> None:
        self._brand_map = brand_map or CANONICAL_BRAND_MAP

    def assess_brand(
        self,
        ocr_text: str | None = None,
        confidence: float | None = None,
    ) -> BrandAssessment:
        """Assess brand name from OCR text string.

        Args:
            ocr_text: Raw OCR extracted text string, or None if no OCR was run.
            confidence: OCR recognition confidence if known.

        Returns:
            A :class:`BrandAssessment` with status CONFIRMED or UNKNOWN.
        """
        if not ocr_text or not ocr_text.strip():
            return BrandAssessment(
                value=None,
                status="UNKNOWN",
                source="none",
                confidence=None,
                raw_text=None,
            )

        cleaned = ocr_text.lower()
        # Word boundary token search
        for token, canonical in self._brand_map.items():
            pattern = rf"\b{re.escape(token)}\b"
            match = re.search(pattern, cleaned)
            if match:
                return BrandAssessment(
                    value=canonical,
                    status="CONFIRMED",
                    source="ocr",
                    confidence=confidence if confidence is not None else 0.85,
                    raw_text=ocr_text[match.start() : match.end()],
                )

        return BrandAssessment(
            value=None,
            status="UNKNOWN",
            source="ocr",
            confidence=None,
            raw_text=None,
        )
