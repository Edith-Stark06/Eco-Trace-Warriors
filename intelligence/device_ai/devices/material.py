"""Material intelligence interface and deterministic device profiles (P5.3).

Provides estimated recoverable material breakdown per canonical device class.
Adheres strictly to the principles:
- Clearly identify source as 'device_profile'.
- Never claim exact physical measurement for an individual device.
- Maintain deterministic, testable, and versioned profiles.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .enrichment_models import MaterialAssessment, MaterialItem

#: Deterministic material composition catalogue per canonical class.
CANONICAL_MATERIAL_PROFILES: dict[str, list[dict[str, object]]] = {
    "laptop": [
        {"material": "Aluminium / Magnesium alloy", "category": "metals", "mass_g": 600.0, "recoverable": True, "hazardous": False},
        {"material": "ABS / PC structural plastics", "category": "plastics", "mass_g": 500.0, "recoverable": True, "hazardous": False},
        {"material": "Multi-layer PCB & IC components", "category": "circuit_boards", "mass_g": 300.0, "recoverable": True, "hazardous": False},
        {"material": "Lithium-ion polymer battery cell", "category": "battery", "mass_g": 300.0, "recoverable": True, "hazardous": True},
        {"material": "Aluminosilicate display glass", "category": "glass", "mass_g": 100.0, "recoverable": True, "hazardous": False},
    ],
    "smartphone": [
        {"material": "Aluminium / Stainless steel frame", "category": "metals", "mass_g": 50.0, "recoverable": True, "hazardous": False},
        {"material": "Tempered display and back glass", "category": "glass", "mass_g": 60.0, "recoverable": True, "hazardous": False},
        {"material": "High-density logic board (PCB)", "category": "circuit_boards", "mass_g": 30.0, "recoverable": True, "hazardous": False},
        {"material": "Lithium-ion battery cell", "category": "battery", "mass_g": 50.0, "recoverable": True, "hazardous": True},
    ],
    "tablet": [
        {"material": "Anodized aluminium enclosure", "category": "metals", "mass_g": 200.0, "recoverable": True, "hazardous": False},
        {"material": "Touch digitizer & LCD glass", "category": "glass", "mass_g": 150.0, "recoverable": True, "hazardous": False},
        {"material": "Lithium-ion polymer battery", "category": "battery", "mass_g": 100.0, "recoverable": True, "hazardous": True},
        {"material": "System logic board (PCB)", "category": "circuit_boards", "mass_g": 30.0, "recoverable": True, "hazardous": False},
    ],
    "monitor": [
        {"material": "Flame-retardant ABS/PC casing", "category": "plastics", "mass_g": 2200.0, "recoverable": True, "hazardous": False},
        {"material": "Steel structural frame & stand", "category": "metals", "mass_g": 1200.0, "recoverable": True, "hazardous": False},
        {"material": "LCD / LED panel substrate glass", "category": "glass", "mass_g": 800.0, "recoverable": True, "hazardous": False},
        {"material": "Power supply and video board", "category": "circuit_boards", "mass_g": 300.0, "recoverable": True, "hazardous": False},
    ],
    "printer": [
        {"material": "Engineering plastics (ABS / HIPS)", "category": "plastics", "mass_g": 4200.0, "recoverable": True, "hazardous": False},
        {"material": "Galvanized steel chassis & rods", "category": "metals", "mass_g": 2200.0, "recoverable": True, "hazardous": False},
        {"material": "Controller & motor driver PCB", "category": "circuit_boards", "mass_g": 400.0, "recoverable": True, "hazardous": False},
        {"material": "Copper stepper motor windings", "category": "metals", "mass_g": 200.0, "recoverable": True, "hazardous": False},
    ],
    "mouse": [
        {"material": "Injection-molded ABS plastic", "category": "plastics", "mass_g": 70.0, "recoverable": True, "hazardous": False},
        {"material": "Optical sensor PCB & switches", "category": "circuit_boards", "mass_g": 15.0, "recoverable": True, "hazardous": False},
        {"material": "Copper USB wiring & connector", "category": "metals", "mass_g": 10.0, "recoverable": True, "hazardous": False},
    ],
    "camera": [
        {"material": "Magnesium / Aluminium alloy body", "category": "metals", "mass_g": 180.0, "recoverable": True, "hazardous": False},
        {"material": "Precision optical lens elements", "category": "glass", "mass_g": 120.0, "recoverable": True, "hazardous": False},
        {"material": "Image processor PCB & sensor", "category": "circuit_boards", "mass_g": 60.0, "recoverable": True, "hazardous": False},
        {"material": "Rechargeable Li-ion battery pack", "category": "battery", "mass_g": 60.0, "recoverable": True, "hazardous": True},
        {"material": "Silicone / Synthetic rubber grip", "category": "plastics", "mass_g": 30.0, "recoverable": False, "hazardous": False},
    ],
    "headphones": [
        {"material": "Polycarbonate headband & earcups", "category": "plastics", "mass_g": 120.0, "recoverable": True, "hazardous": False},
        {"material": "Spring steel band & driver magnets", "category": "metals", "mass_g": 60.0, "recoverable": True, "hazardous": False},
        {"material": "Acoustic driver voice coils (Cu)", "category": "metals", "mass_g": 30.0, "recoverable": True, "hazardous": False},
        {"material": "Memory foam & PU leather cushions", "category": "other", "mass_g": 40.0, "recoverable": False, "hazardous": False},
    ],
}

DEFAULT_FALLBACK_PROFILE: list[dict[str, object]] = [
    {"material": "Mixed engineering plastics", "category": "plastics", "mass_g": 300.0, "recoverable": True, "hazardous": False},
    {"material": "Structural metals", "category": "metals", "mass_g": 150.0, "recoverable": True, "hazardous": False},
    {"material": "General electronics PCB", "category": "circuit_boards", "mass_g": 50.0, "recoverable": True, "hazardous": False},
]


@runtime_checkable
class MaterialIntelligence(Protocol):
    """Protocol interface for material composition intelligence."""

    def assess_materials(
        self,
        device_type: str,
        version: str = "v1.0.0",
    ) -> MaterialAssessment:
        """Assess material composition for a device type."""
        ...


class ProfileBasedMaterialIntelligence:
    """Deterministic material assessor based on canonical device class profiles."""

    def __init__(
        self,
        profiles: dict[str, list[dict[str, object]]] | None = None,
        fallback: list[dict[str, object]] | None = None,
    ) -> None:
        self._profiles = profiles or CANONICAL_MATERIAL_PROFILES
        self._fallback = fallback or DEFAULT_FALLBACK_PROFILE

    def assess_materials(
        self,
        device_type: str,
        version: str = "v1.0.0",
    ) -> MaterialAssessment:
        """Return deterministic material assessment for ``device_type``.

        Args:
            device_type: Canonical device class string (e.g. 'laptop').
            version: Profile catalogue version string.

        Returns:
            A :class:`MaterialAssessment`.
        """
        raw_items = self._profiles.get(device_type.lower(), self._fallback)
        items: list[MaterialItem] = []
        total_g = 0.0

        for r in raw_items:
            item = MaterialItem(
                material=str(r["material"]),
                category=str(r["category"]),
                mass_g=float(r["mass_g"]),
                recoverable=bool(r.get("recoverable", True)),
                hazardous=bool(r.get("hazardous", False)),
                basis="device_profile",
            )
            items.append(item)
            total_g += item.mass_g

        is_known = device_type.lower() in self._profiles
        notes = (
            f"Nominal composition profile for category '{device_type.lower()}'."
            if is_known
            else f"Generic fallback profile applied for unmapped category '{device_type}'."
        )

        return MaterialAssessment(
            materials=items,
            total_mass_g=round(total_g, 2),
            source="device_profile",
            version=version,
            notes=notes,
        )
