"""Tests for the recoverability device-type profiles (milestone M1.8).

Covers the knowledge table itself: canonical lookups, case/whitespace
normalization, synonym aliases, the conservative unknown fallback and the
invariant that every baseline score is a valid ``[0, 1]`` probability.
"""

from device_ai.recoverability.models import HazardLevel
from device_ai.recoverability.profiles import (
    _ALIASES,
    _DEFAULT_PROFILES,
    DeviceProfile,
    profile_for,
)


def test_canonical_lookup_returns_known_profile():
    profile = profile_for("laptop")
    assert profile.known is True
    assert profile.device_type == "laptop"
    assert profile.has_battery is True


def test_lookup_is_case_and_whitespace_insensitive():
    a = profile_for("  CRT  Monitor ")
    b = profile_for("crt monitor")
    c = profile_for("crt_monitor")
    assert a.device_type == b.device_type == c.device_type == "crt_monitor"
    assert a.hazard is HazardLevel.HIGH


def test_synonym_aliases_resolve_to_canonical_profiles():
    assert profile_for("cell phone").device_type == "smartphone"
    assert profile_for("notebook computer").device_type == "laptop"
    assert profile_for("PC").device_type == "desktop"
    assert profile_for("CRT").device_type == "crt_monitor"
    assert profile_for("smart tv").device_type == "television"


def test_unknown_device_falls_back_and_preserves_input_label():
    profile = profile_for("Flux Capacitor")
    assert profile.known is False
    assert profile.hazard is HazardLevel.UNKNOWN
    # The caller-supplied label is preserved (trimmed) for provenance.
    assert profile.device_type == "Flux Capacitor"


def test_empty_device_type_falls_back_to_unknown():
    profile = profile_for("")
    assert profile.known is False
    assert profile.device_type == ""


def test_every_profile_score_is_a_valid_probability():
    profiles = list(_DEFAULT_PROFILES.values())
    assert profiles, "profile table must not be empty"
    for profile in profiles:
        for score in (
            profile.repairability,
            profile.reusability,
            profile.recyclability,
        ):
            assert 0.0 <= score <= 1.0, f"{profile.device_type} out of range"


def test_every_profile_key_matches_its_device_type():
    for key, profile in _DEFAULT_PROFILES.items():
        assert key == profile.device_type


def test_aliases_point_at_real_canonical_keys():
    for alias, canonical in _ALIASES.items():
        assert canonical in _DEFAULT_PROFILES, f"alias {alias!r} dangles"


def test_high_hazard_classes_are_flagged():
    assert profile_for("crt_monitor").hazard is HazardLevel.HIGH
    assert profile_for("battery").hazard is HazardLevel.HIGH


def test_profile_is_immutable():
    profile = profile_for("laptop")
    assert isinstance(profile, DeviceProfile)
    try:
        profile.repairability = 0.1  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("DeviceProfile must be frozen")
