"""Tests for the external material-profile library and loader (milestone M1.10).

The catalogue is stored *outside* the code as a versioned YAML file, so these
tests cover both the shipped catalogue (structure, invariants, coverage parity
with the component profiles) and the loader's validation on hand-written
good/bad catalogues in ``tmp_path`` — no images, no models, no filesystem beyond
the temp catalogue.
"""

import json
from pathlib import Path

import pytest

from device_ai.components.models import ComponentCategory
from device_ai.exceptions import MaterialProfileError
from device_ai.materials.config import DEFAULT_PROFILES_PATH, MaterialConfig
from device_ai.materials.models import MaterialCategory
from device_ai.materials.profiles import (
    MaterialProfileLibrary,
    _normalize,
    load_library,
)

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_SHIPPED = _PACKAGE_ROOT / DEFAULT_PROFILES_PATH


@pytest.fixture()
def library() -> MaterialProfileLibrary:
    """Load the shipped material catalogue once for the suite."""
    return load_library(_SHIPPED)


# --- Shipped catalogue structure & invariants ----------------------------


def test_shipped_catalogue_loads(library):
    assert library.version
    assert library.profiles
    assert library.unknown.known is False


def test_all_masses_are_non_negative(library):
    for profile in library.profiles.values():
        for spec in profile.materials:
            assert spec.mass_g >= 0.0, spec.name
    for spec in library.unknown.materials:
        assert spec.mass_g >= 0.0


def test_every_category_is_a_known_enum_member(library):
    allowed = set(MaterialCategory)
    for profile in library.profiles.values():
        for spec in profile.materials:
            assert spec.category in allowed


def test_every_source_component_is_a_known_component_category(library):
    allowed = set(ComponentCategory.values())
    for profile in library.profiles.values():
        for spec in profile.materials:
            for source in spec.source_components:
                assert source in allowed, (spec.name, source)


def test_every_profile_has_at_least_one_material(library):
    for profile in library.profiles.values():
        assert profile.materials


def test_catalogue_covers_component_device_classes(library):
    # The material catalogue should recognize every device class the component
    # catalogue does, so the two engines resolve the same device types.
    from device_ai.components.config import (
        DEFAULT_PROFILES_PATH as COMPONENT_PROFILES_PATH,
    )
    from device_ai.components.profiles import load_library as load_components

    components = load_components(_PACKAGE_ROOT / COMPONENT_PROFILES_PATH)
    for device_type in components.profiles:
        profile = library.profile_for(device_type)
        assert profile.known, device_type


def test_hazardous_materials_are_present_in_catalogue(library):
    # At least the CRT and battery profiles must flag hazardous materials.
    crt = library.profile_for("crt_monitor")
    assert any(spec.hazardous for spec in crt.materials)
    battery = library.profile_for("battery")
    assert any(spec.hazardous for spec in battery.materials)


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
    assert profile.materials  # generic materials are present


# --- Loader validation (hand-written catalogues) -------------------------


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_file_raises(tmp_path):
    with pytest.raises(MaterialProfileError):
        load_library(tmp_path / "nope.yaml")


def test_malformed_yaml_raises(tmp_path):
    bad = _write(tmp_path / "m.yaml", "version: '1'\nprofiles: [::::\n")
    with pytest.raises(MaterialProfileError):
        load_library(bad)


def test_missing_version_raises(tmp_path):
    bad = _write(
        tmp_path / "m.yaml",
        "profiles:\n  laptop:\n    materials:\n"
        "      - {name: X, category: plastic, mass_g: 5}\n"
        "unknown:\n  materials:\n"
        "      - {name: Y, category: other, mass_g: 5}\n",
    )
    with pytest.raises(MaterialProfileError):
        load_library(bad)


def test_unknown_category_raises(tmp_path):
    bad = _write(
        tmp_path / "m.yaml",
        "version: '1'\nprofiles:\n  laptop:\n    materials:\n"
        "      - {name: X, category: unobtanium, mass_g: 5}\n"
        "unknown:\n  materials:\n"
        "      - {name: Y, category: other, mass_g: 5}\n",
    )
    with pytest.raises(MaterialProfileError):
        load_library(bad)


def test_negative_mass_raises(tmp_path):
    bad = _write(
        tmp_path / "m.yaml",
        "version: '1'\nprofiles:\n  laptop:\n    materials:\n"
        "      - {name: X, category: plastic, mass_g: -1}\n"
        "unknown:\n  materials:\n"
        "      - {name: Y, category: other, mass_g: 5}\n",
    )
    with pytest.raises(MaterialProfileError):
        load_library(bad)


def test_non_numeric_mass_raises(tmp_path):
    bad = _write(
        tmp_path / "m.yaml",
        "version: '1'\nprofiles:\n  laptop:\n    materials:\n"
        "      - {name: X, category: plastic, mass_g: heavy}\n"
        "unknown:\n  materials:\n"
        "      - {name: Y, category: other, mass_g: 5}\n",
    )
    with pytest.raises(MaterialProfileError):
        load_library(bad)


def test_bad_source_component_raises(tmp_path):
    bad = _write(
        tmp_path / "m.yaml",
        "version: '1'\nprofiles:\n  laptop:\n    materials:\n"
        "      - name: X\n        category: plastic\n"
        "        mass_g: 5\n        source_components: [warp_core]\n"
        "unknown:\n  materials:\n"
        "      - {name: Y, category: other, mass_g: 5}\n",
    )
    with pytest.raises(MaterialProfileError):
        load_library(bad)


def test_alias_to_unknown_type_raises(tmp_path):
    bad = _write(
        tmp_path / "m.yaml",
        "version: '1'\naliases:\n  foo: ghost\nprofiles:\n  laptop:\n"
        "    materials:\n"
        "      - {name: X, category: plastic, mass_g: 5}\n"
        "unknown:\n  materials:\n"
        "      - {name: Y, category: other, mass_g: 5}\n",
    )
    with pytest.raises(MaterialProfileError):
        load_library(bad)


def test_missing_unknown_fallback_raises(tmp_path):
    bad = _write(
        tmp_path / "m.yaml",
        "version: '1'\nprofiles:\n  laptop:\n    materials:\n"
        "      - {name: X, category: plastic, mass_g: 5}\n",
    )
    with pytest.raises(MaterialProfileError):
        load_library(bad)


def test_empty_materials_list_raises(tmp_path):
    bad = _write(
        tmp_path / "m.yaml",
        "version: '1'\nprofiles:\n  laptop:\n    materials: []\n"
        "unknown:\n  materials:\n"
        "      - {name: Y, category: other, mass_g: 5}\n",
    )
    with pytest.raises(MaterialProfileError):
        load_library(bad)


# --- JSON catalogue parity ------------------------------------------------


def test_json_catalogue_loads(tmp_path):
    doc = {
        "version": "9.9.9",
        "aliases": {"lappy": "laptop"},
        "profiles": {
            "laptop": {
                "materials": [
                    {"name": "Steel", "category": "ferrous_metal", "mass_g": 100.0}
                ]
            }
        },
        "unknown": {
            "materials": [{"name": "Plastic", "category": "plastic", "mass_g": 50.0}]
        },
    }
    path = tmp_path / "m.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    library = load_library(path)
    assert library.version == "9.9.9"
    assert library.profile_for("lappy").device_type == "laptop"


# --- from_settings mapping ------------------------------------------------


def test_config_from_settings_maps_env_knobs():
    from device_ai.configs.settings import Settings

    settings = Settings(
        material_profiles_path="custom/path.yaml",
        material_min_confidence=0.2,
    )
    config = MaterialConfig.from_settings(settings)
    assert config.profiles_path == "custom/path.yaml"
    assert config.min_material_confidence == 0.2


def test_normalize_collapses_whitespace_and_casefolds():
    assert _normalize("  CRT  Monitor ") == "crt_monitor"
