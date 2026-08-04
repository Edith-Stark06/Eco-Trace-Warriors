"""Device-type recoverability profiles (milestone M1.8).

A :class:`DeviceProfile` is the deterministic, hand-curated knowledge the engine
holds about a *class* of device before it looks at any specific unit: the
baseline ease of repair, fitness for reuse and material recyclability, the
intrinsic hazard the device carries, and whether it contains a battery. These
baselines are the seed the rule engine adjusts using the evidence in a fused
:class:`~device_ai.fusion.models.DeviceContext`.

The table is intentionally small, explicit and value-only (no logic) so it can
be audited and extended without touching the rules or scoring. Lookups are
normalized (case/whitespace-insensitive) and understand common synonyms, so a
detector emitting ``"Laptop Computer"`` and an OCR label of ``"laptop"`` resolve
to the same profile. Anything unrecognized falls back to a conservative
``known=False`` profile that the ``UnknownDeviceRule`` turns into a
manual-review recommendation.

Every score in the table lies in ``[0, 1]``; this is asserted by the tests.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .models import HazardLevel


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    """The baseline recoverability knowledge for one class of device.

    Attributes:
        device_type: Canonical (or, for the fallback, the caller-supplied)
            device type this profile describes.
        repairability: Baseline ``[0, 1]`` ease-of-repair for the class.
        reusability: Baseline ``[0, 1]`` fitness-for-reuse for the class.
        recyclability: Baseline ``[0, 1]`` material-recovery for the class.
        hazard: Intrinsic hazard the class carries independent of its battery
            (e.g. leaded CRT glass, toner); battery hazard is layered on by a
            dedicated rule using :attr:`has_battery`.
        has_battery: Whether the class typically embeds a battery (a distinct
            handling/hazard concern the battery rule escalates).
        known: Whether this is a recognized profile (``False`` only for the
            unknown fallback, which forces manual review).
        notes: Short human-readable rationale for the baseline (provenance).
    """

    device_type: str
    repairability: float
    reusability: float
    recyclability: float
    hazard: HazardLevel
    has_battery: bool
    known: bool = True
    notes: str = ""


# The conservative fallback for any device type the table does not recognize.
# It scores everything at a neutral-low baseline and is flagged ``known=False``
# so the rule engine forces a manual review rather than guessing a disposition.
_UNKNOWN_PROFILE = DeviceProfile(
    device_type="",
    repairability=0.30,
    reusability=0.30,
    recyclability=0.40,
    hazard=HazardLevel.UNKNOWN,
    has_battery=False,
    known=False,
    notes="Unrecognized device type; disposition requires manual review.",
)


# The curated device-type knowledge table, keyed by normalized canonical type.
# Values are deliberate, documented baselines — not learned — so they can be
# reviewed and tuned in one place without touching engine logic.
_DEFAULT_PROFILES: dict[str, DeviceProfile] = {
    profile.device_type: profile
    for profile in (
        DeviceProfile(
            "laptop",
            0.75,
            0.80,
            0.85,
            HazardLevel.LOW,
            True,
            notes="Modular, high resale and material value; embedded battery.",
        ),
        DeviceProfile(
            "smartphone",
            0.55,
            0.75,
            0.80,
            HazardLevel.LOW,
            True,
            notes="Strong resale/parts market; glued assembly limits repair.",
        ),
        DeviceProfile(
            "tablet",
            0.50,
            0.72,
            0.78,
            HazardLevel.LOW,
            True,
            notes="Glued glass/battery lowers repair; good reuse value.",
        ),
        DeviceProfile(
            "desktop",
            0.85,
            0.75,
            0.88,
            HazardLevel.NONE,
            False,
            notes="Highly modular and serviceable; no battery.",
        ),
        DeviceProfile(
            "server",
            0.80,
            0.70,
            0.90,
            HazardLevel.NONE,
            False,
            notes="Serviceable, high-value metals; enterprise reuse channels.",
        ),
        DeviceProfile(
            "monitor",
            0.55,
            0.60,
            0.75,
            HazardLevel.LOW,
            False,
            notes="Flat-panel display; some backlight/board hazard.",
        ),
        DeviceProfile(
            "crt_monitor",
            0.20,
            0.15,
            0.45,
            HazardLevel.HIGH,
            False,
            notes="Leaded glass and phosphor coating; hazardous handling.",
        ),
        DeviceProfile(
            "television",
            0.35,
            0.45,
            0.65,
            HazardLevel.MEDIUM,
            False,
            notes="Large panel/board assembly; mixed hazard by vintage.",
        ),
        DeviceProfile(
            "printer",
            0.50,
            0.50,
            0.65,
            HazardLevel.MEDIUM,
            False,
            notes="Toner/ink residue and rollers complicate handling.",
        ),
        DeviceProfile(
            "keyboard",
            0.60,
            0.65,
            0.80,
            HazardLevel.NONE,
            False,
            notes="Simple, largely plastic/metal; readily recyclable.",
        ),
        DeviceProfile(
            "mouse",
            0.55,
            0.60,
            0.78,
            HazardLevel.NONE,
            False,
            notes="Small peripheral; straightforward material recovery.",
        ),
        DeviceProfile(
            "router",
            0.55,
            0.65,
            0.80,
            HazardLevel.LOW,
            False,
            notes="Networking board; steady reuse and recycling value.",
        ),
        DeviceProfile(
            "power_supply",
            0.45,
            0.50,
            0.82,
            HazardLevel.LOW,
            False,
            notes="Capacitors carry residual charge; metal-rich recovery.",
        ),
        DeviceProfile(
            "cable",
            0.30,
            0.55,
            0.90,
            HazardLevel.NONE,
            False,
            notes="Copper-rich; low repair but excellent material recovery.",
        ),
        DeviceProfile(
            "camera",
            0.45,
            0.65,
            0.72,
            HazardLevel.LOW,
            True,
            notes="Optics/board; battery present in most units.",
        ),
        DeviceProfile(
            "game_console",
            0.60,
            0.75,
            0.80,
            HazardLevel.LOW,
            False,
            notes="Serviceable and high resale; strong reuse market.",
        ),
        DeviceProfile(
            "smartwatch",
            0.35,
            0.60,
            0.70,
            HazardLevel.LOW,
            True,
            notes="Sealed wearable; small embedded battery.",
        ),
        DeviceProfile(
            "headphones",
            0.40,
            0.60,
            0.72,
            HazardLevel.LOW,
            True,
            notes="Wireless units embed a small battery; modest repair.",
        ),
        DeviceProfile(
            "battery",
            0.10,
            0.10,
            0.70,
            HazardLevel.HIGH,
            True,
            notes="Standalone cell/pack; hazardous, recycle via dedicated stream.",
        ),
    )
}


# Common synonyms and vendor phrasings mapped onto the canonical keys above, so
# heterogeneous module labels ("cell phone", "CRT", "PC") resolve consistently.
_ALIASES: dict[str, str] = {
    "laptop_computer": "laptop",
    "notebook": "laptop",
    "notebook_computer": "laptop",
    "ultrabook": "laptop",
    "cell_phone": "smartphone",
    "cellphone": "smartphone",
    "mobile_phone": "smartphone",
    "mobile": "smartphone",
    "phone": "smartphone",
    "smart_phone": "smartphone",
    "handset": "smartphone",
    "desktop_computer": "desktop",
    "personal_computer": "desktop",
    "pc": "desktop",
    "workstation": "desktop",
    "tower": "desktop",
    "crt": "crt_monitor",
    "cathode_ray_tube": "crt_monitor",
    "lcd_monitor": "monitor",
    "led_monitor": "monitor",
    "display": "monitor",
    "screen": "monitor",
    "tv": "television",
    "smart_tv": "television",
    "wifi_router": "router",
    "wireless_router": "router",
    "modem": "router",
    "gateway": "router",
    "power_adapter": "power_supply",
    "power_brick": "power_supply",
    "charger": "power_supply",
    "psu": "power_supply",
    "adapter": "power_supply",
    "gaming_console": "game_console",
    "console": "game_console",
    "digital_camera": "camera",
    "webcam": "camera",
    "wearable": "smartwatch",
    "smart_watch": "smartwatch",
    "earbuds": "headphones",
    "earphones": "headphones",
    "headset": "headphones",
    "battery_pack": "battery",
    "cell": "battery",
    "usb_cable": "cable",
    "power_cable": "cable",
    "wire": "cable",
}


def _normalize(device_type: str) -> str:
    """Return the lookup key for ``device_type``.

    Collapses internal whitespace to single underscores and casefolds, so
    ``"  CRT  Monitor "`` and ``"crt monitor"`` both become ``"crt_monitor"``.
    """
    return "_".join(device_type.split()).casefold()


def profile_for(device_type: str) -> DeviceProfile:
    """Resolve the :class:`DeviceProfile` for a device type.

    The lookup is normalized (case/whitespace-insensitive) and understands the
    synonyms in ``_ALIASES``. Unrecognized types return a copy of the
    conservative unknown fallback, stamped with the caller-supplied
    ``device_type`` for provenance.

    Args:
        device_type: The (possibly messy) device type from a device context.

    Returns:
        The matching :class:`DeviceProfile`, or the unknown fallback.
    """
    key = _normalize(device_type)
    key = _ALIASES.get(key, key)
    profile = _DEFAULT_PROFILES.get(key)
    if profile is not None:
        return profile
    return replace(_UNKNOWN_PROFILE, device_type=device_type.strip())
