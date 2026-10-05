"""Tests for the external component-profile library and loader (milestone M1.9).

The catalogue is stored *outside* the code as a versioned YAML file, so these
tests cover both the shipped catalogue (structure, invariants, coverage parity
with the recoverability profiles) and the loader's validation on hand-written
good/bad catalogues in ``tmp_path`` — no images, no models, no filesystem beyond
the temp catalogue.
"""

import json
from pathlib import Path

import pytest

from device_ai.components.config import DEFAULT_PROFILES_PATH, ComponentConfig
from device_ai.components.models import ComponentCategory
from device_ai.components.profiles import (
    ComponentProfileLibrary,
    _normalize,
    load_library,
)
from device_ai.exceptions import ComponentProfileError
from device_ai.recoverability.profiles import _DEFAULT_PROFILES

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_SHIPPED = _PACKAGE_ROOT / DEFAULT_PROFILES_PATH


@pytest.fixture()
def library() -> ComponentProfileLibrary:
    """Load the shipped component catalogue once for the suite."""
    return load_library(_SHIPPED)


# --- Shipped catalogue structure & invariants ----------------------------


def test_shipped_catalogue_loads(library):
    assert library.version
    assert library.profiles
    assert library.unknown.known is False


def test_all_base_likelihoods_are_valid_probabilities(library):
    for profile in library.profiles.values():
        for spec in profile.components:
            assert 0.0 <= spec.base_likelihood <= 1.0, spec.name
    for spec in library.unknown.components:
        assert 0.0 <= spec.base_likelihood <= 1.0


def test_every_category_is_a_known_enum_member(library):
    allowed = set(ComponentCategory)
    for profile in library.profiles.values():
        for spec in profile.components:
            assert spec.category in allowed


def test_every_profile_has_at_least_one_component(library):
    for profile in library.profiles.values():
        assert profile.components


def test_catalogue_covers_recoverability_device_classes(library):
    # The component catalogue should recognize every recoverability class so the
    # two engines resolve the same device types.
    for device_type in _DEFAULT_PROFILES:
        profile = library.profile_for(device_type)
        assert profile.known, device_type


# --- Lookup, normalization & aliases -------------------------------------


def test_profile_for_is_case_and_whitespace_insensitive(library):
    a = library.profile_for("  LAPTOP  ")
    b = library.profile_for("laptop")
    assert a.device_type == b.device_type == "laptop"


def test_profile_for_resolves_aliases(library):
    assert library.profile_for("cell phone").device_type == "smartphone"
    assert library.profile_for("PC").device_type == "desktop"
    assert library.profile_for("CRT").device_type == "crt_monitor"


def test_every_alias_points_at_a_real_profile(library):
    for canonical in library.aliases.values():
        assert canonical in library.profiles


def test_unknown_type_returns_fallback_with_caller_label(library):
    profile = library.profile_for("Teleporter")
    assert profile.known is False
    assert profile.device_type == "Teleporter"
    assert profile.components  # generic components are present


def test_battery_components_flagged_hazardous(library):
    battery = library.profile_for("battery")
    assert any(spec.hazardous for spec in battery.components)


def test_implied_by_signals_are_recognized(library):
    laptop = library.profile_for("laptop")
    implied = {signal for spec in laptop.components for signal in spec.implied_by}
    assert implied  # laptop mainboard/storage are implied by serial number
    assert implied <= {"model", "serial_number", "imei", "mac_address"}


# --- Loader validation (hand-written catalogues) -------------------------


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_file_raises(tmp_path):
    with pytest.raises(ComponentProfileError):
        load_library(tmp_path / "nope.yaml")


def test_malformed_yaml_raises(tmp_path):
    bad = _write(tmp_path / "c.yaml", "version: '1'\nprofiles: [::::\n")
    with pytest.raises(ComponentProfileError):
        load_library(bad)


def test_missing_version_raises(tmp_path):
    bad = _write(
        tmp_path / "c.yaml",
        "profiles:\n  laptop:\n    components:\n"
        "      - {name: X, category: battery, base_likelihood: 0.5}\n"
        "unknown:\n  components:\n"
        "      - {name: Y, category: other, base_likelihood: 0.5}\n",
    )
    with pytest.raises(ComponentProfileError):
        load_library(bad)


def test_unknown_category_raises(tmp_path):
    bad = _write(
        tmp_path / "c.yaml",
        "version: '1'\nprofiles:\n  laptop:\n    components:\n"
        "      - {name: X, category: warp_core, base_likelihood: 0.5}\n"
        "unknown:\n  components:\n"
        "      - {name: Y, category: other, base_likelihood: 0.5}\n",
    )
    with pytest.raises(ComponentProfileError):
        load_library(bad)


def test_out_of_range_likelihood_raises(tmp_path):
    bad = _write(
        tmp_path / "c.yaml",
        "version: '1'\nprofiles:\n  laptop:\n    components:\n"
        "      - {name: X, category: battery, base_likelihood: 1.5}\n"
        "unknown:\n  components:\n"
        "      - {name: Y, category: other, base_likelihood: 0.5}\n",
    )
    with pytest.raises(ComponentProfileError):
        load_library(bad)


def test_alias_to_unknown_type_raises(tmp_path):
    bad = _write(
        tmp_path / "c.yaml",
        "version: '1'\naliases:\n  foo: ghost\nprofiles:\n  laptop:\n"
        "    components:\n"
        "      - {name: X, category: battery, base_likelihood: 0.5}\n"
        "unknown:\n  components:\n"
        "      - {name: Y, category: other, base_likelihood: 0.5}\n",
    )
    with pytest.raises(ComponentProfileError):
        load_library(bad)


def test_missing_unknown_fallback_raises(tmp_path):
    bad = _write(
        tmp_path / "c.yaml",
        "version: '1'\nprofiles:\n  laptop:\n    components:\n"
        "      - {name: X, category: battery, base_likelihood: 0.5}\n",
    )
    with pytest.raises(ComponentProfileError):
        load_library(bad)


def test_empty_components_list_raises(tmp_path):
    bad = _write(
        tmp_path / "c.yaml",
        "version: '1'\nprofiles:\n  laptop:\n    components: []\n"
        "unknown:\n  components:\n"
        "      - {name: Y, category: other, base_likelihood: 0.5}\n",
    )
    with pytest.raises(ComponentProfileError):
        load_library(bad)


def test_bad_implied_by_signal_raises(tmp_path):
    bad = _write(
        tmp_path / "c.yaml",
        "version: '1'\nprofiles:\n  laptop:\n    components:\n"
        "      - name: X\n        category: battery\n"
        "        base_likelihood: 0.5\n        implied_by: [color]\n"
        "unknown:\n  components:\n"
        "      - {name: Y, category: other, base_likelihood: 0.5}\n",
    )
    with pytest.raises(ComponentProfileError):
        load_library(bad)


# --- JSON catalogue parity ------------------------------------------------


def test_json_catalogue_loads(tmp_path):
    doc = {
        "version": "9.9.9",
        "aliases": {"lappy": "laptop"},
        "profiles": {
            "laptop": {
                "components": [
                    {"name": "Battery", "category": "battery", "base_likelihood": 0.9}
                ]
            }
        },
        "unknown": {
            "components": [
                {"name": "Housing", "category": "housing", "base_likelihood": 0.8}
            ]
        },
    }
    path = tmp_path / "c.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    library = load_library(path)
    assert library.version == "9.9.9"
    assert library.profile_for("lappy").device_type == "laptop"


# --- from_settings mapping ------------------------------------------------


def test_config_from_settings_maps_env_knobs():
    from device_ai.configs.settings import Settings

    settings = Settings(
        component_profiles_path="custom/path.yaml",
        component_min_presence_confidence=0.2,
    )
    config = ComponentConfig.from_settings(settings)
    assert config.profiles_path == "custom/path.yaml"
    assert config.min_presence_confidence == 0.2


def test_normalize_collapses_whitespace_and_casefolds():
    assert _normalize("  CRT  Monitor ") == "crt_monitor"
