"""Tests for the external conversion-factor library and loader (M1.11).

The catalogue is stored *outside* the code as a versioned YAML file, so these
tests cover both the shipped catalogue (structure, invariants, coverage parity
with the material categories) and the loader's validation on hand-written
good/bad catalogues in ``tmp_path`` — no images, no models, no filesystem beyond
the temp catalogue.
"""

import json
from pathlib import Path

import pytest

from device_ai.environmental.config import DEFAULT_FACTORS_PATH
from device_ai.environmental.factors import (
    FactorLibrary,
    MaterialFactor,
    load_library,
)
from device_ai.exceptions import EnvironmentalFactorError
from device_ai.materials.models import MaterialCategory

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_SHIPPED = _PACKAGE_ROOT / DEFAULT_FACTORS_PATH


@pytest.fixture()
def library() -> FactorLibrary:
    """Load the shipped conversion-factor catalogue once for the suite."""
    return load_library(_SHIPPED)


# --- Shipped catalogue structure & invariants ----------------------------


def test_shipped_catalogue_loads(library):
    assert library.version
    assert library.factors
    assert isinstance(library.default, MaterialFactor)


def test_all_factors_are_non_negative(library):
    for factor in library.factors.values():
        assert factor.carbon_kg_per_kg >= 0.0
        assert factor.energy_mj_per_kg >= 0.0
        assert factor.water_l_per_kg >= 0.0
    assert library.default.carbon_kg_per_kg >= 0.0


def test_every_key_is_a_known_material_category(library):
    allowed = set(MaterialCategory)
    for category in library.factors:
        assert category in allowed


def test_catalogue_covers_every_material_category(library):
    # A factor for every category means the engine never silently falls back to
    # the generic default for a material the material engine can actually emit.
    for category in MaterialCategory:
        assert category in library.factors, category


def test_critical_categories_are_flagged_critical(library):
    for category in (
        MaterialCategory.PRECIOUS_METAL,
        MaterialCategory.CRITICAL_MATERIAL,
        MaterialCategory.RARE_EARTH,
    ):
        assert library.factors[category].critical is True


def test_precious_metal_has_the_largest_carbon_factor(library):
    # Virgin precious-metal extraction dwarfs every other category, so recovering
    # even a little of it should carry the biggest per-kg avoided burden.
    precious = library.factors[MaterialCategory.PRECIOUS_METAL].carbon_kg_per_kg
    for category, factor in library.factors.items():
        if category is not MaterialCategory.PRECIOUS_METAL:
            assert factor.carbon_kg_per_kg <= precious


# --- factor_for lookup & fallback ----------------------------------------


def test_factor_for_returns_named_factor(library):
    factor = library.factor_for(MaterialCategory.FERROUS_METAL)
    assert factor.category is MaterialCategory.FERROUS_METAL


def test_factor_for_unknown_category_uses_default():
    # A catalogue that omits a category resolves it to the default, re-stamped
    # with the requested category.
    library = FactorLibrary(
        version="t",
        factors={
            MaterialCategory.PLASTIC: MaterialFactor(
                category=MaterialCategory.PLASTIC,
                carbon_kg_per_kg=2.0,
                energy_mj_per_kg=60.0,
                water_l_per_kg=50.0,
            )
        },
        default=MaterialFactor(
            category=MaterialCategory.OTHER,
            carbon_kg_per_kg=1.5,
            energy_mj_per_kg=20.0,
            water_l_per_kg=20.0,
        ),
    )
    resolved = library.factor_for(MaterialCategory.GLASS)
    assert resolved.category is MaterialCategory.GLASS
    assert resolved.carbon_kg_per_kg == 1.5


# --- Loader validation (hand-written catalogues) -------------------------


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


_GOOD_DEFAULT = (
    "default:\n"
    "  carbon_kg_per_kg: 1.5\n"
    "  energy_mj_per_kg: 20\n"
    "  water_l_per_kg: 20\n"
)


def test_missing_file_raises(tmp_path):
    with pytest.raises(EnvironmentalFactorError):
        load_library(tmp_path / "nope.yaml")


def test_malformed_yaml_raises(tmp_path):
    bad = _write(tmp_path / "f.yaml", "version: '1'\nfactors: [::::\n")
    with pytest.raises(EnvironmentalFactorError):
        load_library(bad)


def test_missing_version_raises(tmp_path):
    bad = _write(
        tmp_path / "f.yaml",
        "factors:\n  plastic:\n"
        "    {carbon_kg_per_kg: 2, energy_mj_per_kg: 60, water_l_per_kg: 50}\n"
        + _GOOD_DEFAULT,
    )
    with pytest.raises(EnvironmentalFactorError):
        load_library(bad)


def test_unknown_category_raises(tmp_path):
    bad = _write(
        tmp_path / "f.yaml",
        "version: '1'\nfactors:\n  unobtanium:\n"
        "    {carbon_kg_per_kg: 2, energy_mj_per_kg: 60, water_l_per_kg: 50}\n"
        + _GOOD_DEFAULT,
    )
    with pytest.raises(EnvironmentalFactorError):
        load_library(bad)


def test_negative_factor_raises(tmp_path):
    bad = _write(
        tmp_path / "f.yaml",
        "version: '1'\nfactors:\n  plastic:\n"
        "    {carbon_kg_per_kg: -2, energy_mj_per_kg: 60, water_l_per_kg: 50}\n"
        + _GOOD_DEFAULT,
    )
    with pytest.raises(EnvironmentalFactorError):
        load_library(bad)


def test_non_numeric_factor_raises(tmp_path):
    bad = _write(
        tmp_path / "f.yaml",
        "version: '1'\nfactors:\n  plastic:\n"
        "    {carbon_kg_per_kg: heavy, energy_mj_per_kg: 60, water_l_per_kg: 50}\n"
        + _GOOD_DEFAULT,
    )
    with pytest.raises(EnvironmentalFactorError):
        load_library(bad)


def test_missing_numeric_field_raises(tmp_path):
    bad = _write(
        tmp_path / "f.yaml",
        "version: '1'\nfactors:\n  plastic:\n"
        "    {carbon_kg_per_kg: 2, energy_mj_per_kg: 60}\n" + _GOOD_DEFAULT,  # no water
    )
    with pytest.raises(EnvironmentalFactorError):
        load_library(bad)


def test_no_factors_raises(tmp_path):
    bad = _write(tmp_path / "f.yaml", "version: '1'\nfactors: {}\n" + _GOOD_DEFAULT)
    with pytest.raises(EnvironmentalFactorError):
        load_library(bad)


def test_missing_default_fallback_raises(tmp_path):
    bad = _write(
        tmp_path / "f.yaml",
        "version: '1'\nfactors:\n  plastic:\n"
        "    {carbon_kg_per_kg: 2, energy_mj_per_kg: 60, water_l_per_kg: 50}\n",
    )
    with pytest.raises(EnvironmentalFactorError):
        load_library(bad)


def test_bool_is_rejected_as_numeric(tmp_path):
    # ``True`` is an int subclass in Python; the loader must not accept it as a
    # factor value.
    bad = _write(
        tmp_path / "f.yaml",
        "version: '1'\nfactors:\n  plastic:\n"
        "    {carbon_kg_per_kg: true, energy_mj_per_kg: 60, water_l_per_kg: 50}\n"
        + _GOOD_DEFAULT,
    )
    with pytest.raises(EnvironmentalFactorError):
        load_library(bad)


# --- JSON catalogue parity ------------------------------------------------


def test_json_catalogue_loads(tmp_path):
    doc = {
        "version": "9.9.9",
        "factors": {
            "ferrous_metal": {
                "carbon_kg_per_kg": 1.5,
                "energy_mj_per_kg": 20.0,
                "water_l_per_kg": 20.0,
            }
        },
        "default": {
            "carbon_kg_per_kg": 1.0,
            "energy_mj_per_kg": 10.0,
            "water_l_per_kg": 10.0,
        },
    }
    path = tmp_path / "f.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    library = load_library(path)
    assert library.version == "9.9.9"
    assert library.factor_for(MaterialCategory.FERROUS_METAL).carbon_kg_per_kg == 1.5


# --- from_settings mapping ------------------------------------------------


def test_config_from_settings_maps_env_knobs():
    from device_ai.configs.settings import Settings
    from device_ai.environmental.config import EnvironmentalConfig

    settings = Settings(
        environmental_factors_path="custom/path.yaml",
        environmental_min_confidence=0.2,
    )
    config = EnvironmentalConfig.from_settings(settings)
    assert config.factors_path == "custom/path.yaml"
    assert config.min_material_confidence == 0.2
