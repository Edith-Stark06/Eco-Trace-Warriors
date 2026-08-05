"""Tests for the external decision-knowledge catalogue and loader (M2.1).

The catalogue is stored *outside* the code as a versioned YAML file, so these
tests cover both the shipped catalogue (structure, invariants, coverage of every
dimension and confidence source) and the loader's aggressive validation on
hand-written good/bad catalogues in ``tmp_path`` — no images, no models, no
filesystem beyond the temp catalogue.
"""

import json
from pathlib import Path

import pytest

from device_ai.decision.config import DEFAULT_KNOWLEDGE_PATH
from device_ai.decision.knowledge import (
    CANONICAL_SIGNALS,
    CONFIDENCE_SOURCES,
    KnowledgeBase,
    Normalization,
    load_knowledge,
)
from device_ai.decision.models import DecisionDimension
from device_ai.exceptions import DecisionKnowledgeError

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_SHIPPED = _PACKAGE_ROOT / DEFAULT_KNOWLEDGE_PATH


@pytest.fixture()
def knowledge() -> KnowledgeBase:
    """Load the shipped decision-knowledge catalogue once for the suite."""
    return load_knowledge(_SHIPPED)


# --- Shipped catalogue structure & invariants ----------------------------


def test_shipped_catalogue_loads(knowledge):
    assert knowledge.version
    assert isinstance(knowledge.normalization, Normalization)
    assert knowledge.dimensions
    assert knowledge.confidence_weights


def test_catalogue_defines_every_dimension(knowledge):
    # Every decision dimension must be weighted; the loader rejects a catalogue
    # that omits one, so this also guards against a silently-dropped dimension.
    for dimension in DecisionDimension:
        assert dimension in knowledge.dimensions, dimension


def test_every_dimension_uses_only_canonical_signals(knowledge):
    for dimension, weights in knowledge.dimensions.items():
        assert weights, dimension
        for name in weights:
            assert name in CANONICAL_SIGNALS, (dimension, name)


def test_every_dimension_has_a_positive_weight(knowledge):
    for dimension, weights in knowledge.dimensions.items():
        assert any(weight > 0.0 for weight in weights.values()), dimension
        assert all(weight >= 0.0 for weight in weights.values()), dimension


def test_confidence_weights_cover_only_known_sources(knowledge):
    assert set(knowledge.confidence_weights) <= CONFIDENCE_SOURCES
    assert any(weight > 0.0 for weight in knowledge.confidence_weights.values())


def test_normalization_constants_are_strictly_positive(knowledge):
    norm = knowledge.normalization
    assert norm.carbon_saturation_kg > 0.0
    assert norm.energy_saturation_mj > 0.0
    assert norm.water_saturation_l > 0.0
    assert norm.critical_recovery_saturation_kg > 0.0


def test_weights_for_returns_named_map(knowledge):
    weights = knowledge.weights_for(DecisionDimension.REPAIRABILITY)
    assert "repairability" in weights


# --- Loader validation (hand-written catalogues) -------------------------


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


_GOOD_NORMALIZATION = (
    "normalization:\n"
    "  carbon_saturation_kg: 100.0\n"
    "  energy_saturation_mj: 1500.0\n"
    "  water_saturation_l: 1000.0\n"
    "  critical_recovery_saturation_kg: 0.05\n"
)

_GOOD_CONFIDENCE = (
    "confidence:\n"
    "  recoverability: 0.2\n"
    "  components: 0.15\n"
    "  materials: 0.25\n"
    "  environmental: 0.25\n"
    "  fusion: 0.15\n"
)


def _all_dimensions(body: str = "\n    repairability: 1.0\n") -> str:
    """Return a ``dimensions`` block naming every dimension with ``body``."""
    lines = ["dimensions:"]
    for dimension in DecisionDimension.values():
        lines.append(f"  {dimension}:{body.rstrip()}")
    return "\n".join(lines) + "\n"


def _good_catalogue() -> str:
    return (
        'version: "1.0.0"\n'
        + _GOOD_NORMALIZATION
        + _all_dimensions()
        + _GOOD_CONFIDENCE
    )


def test_hand_written_good_catalogue_loads(tmp_path):
    good = _write(tmp_path / "k.yaml", _good_catalogue())
    knowledge = load_knowledge(good)
    assert knowledge.version == "1.0.0"
    assert set(knowledge.dimensions) == set(DecisionDimension)


def test_missing_file_raises(tmp_path):
    with pytest.raises(DecisionKnowledgeError):
        load_knowledge(tmp_path / "nope.yaml")


def test_malformed_yaml_raises(tmp_path):
    bad = _write(tmp_path / "k.yaml", "version: '1'\ndimensions: [::::\n")
    with pytest.raises(DecisionKnowledgeError):
        load_knowledge(bad)


def test_empty_catalogue_raises(tmp_path):
    bad = _write(tmp_path / "k.yaml", "")
    with pytest.raises(DecisionKnowledgeError):
        load_knowledge(bad)


def test_missing_version_raises(tmp_path):
    bad = _write(
        tmp_path / "k.yaml",
        _GOOD_NORMALIZATION + _all_dimensions() + _GOOD_CONFIDENCE,
    )
    with pytest.raises(DecisionKnowledgeError):
        load_knowledge(bad)


def test_missing_normalization_raises(tmp_path):
    bad = _write(
        tmp_path / "k.yaml",
        'version: "1"\n' + _all_dimensions() + _GOOD_CONFIDENCE,
    )
    with pytest.raises(DecisionKnowledgeError):
        load_knowledge(bad)


def test_non_positive_saturation_constant_raises(tmp_path):
    bad = _write(
        tmp_path / "k.yaml",
        'version: "1"\n'
        "normalization:\n"
        "  carbon_saturation_kg: 0.0\n"  # not strictly positive
        "  energy_saturation_mj: 1500.0\n"
        "  water_saturation_l: 1000.0\n"
        "  critical_recovery_saturation_kg: 0.05\n"
        + _all_dimensions()
        + _GOOD_CONFIDENCE,
    )
    with pytest.raises(DecisionKnowledgeError):
        load_knowledge(bad)


def test_missing_dimension_raises(tmp_path):
    # Only repairability is defined; the other five are missing.
    bad = _write(
        tmp_path / "k.yaml",
        'version: "1"\n'
        + _GOOD_NORMALIZATION
        + "dimensions:\n  repairability:\n    repairability: 1.0\n"
        + _GOOD_CONFIDENCE,
    )
    with pytest.raises(DecisionKnowledgeError):
        load_knowledge(bad)


def test_unknown_dimension_raises(tmp_path):
    bad = _write(
        tmp_path / "k.yaml",
        'version: "1"\n'
        + _GOOD_NORMALIZATION
        + _all_dimensions()
        + "  teleportability:\n    repairability: 1.0\n"
        + _GOOD_CONFIDENCE,
    )
    with pytest.raises(DecisionKnowledgeError):
        load_knowledge(bad)


def test_unknown_signal_name_raises(tmp_path):
    bad = _write(
        tmp_path / "k.yaml",
        'version: "1"\n'
        + _GOOD_NORMALIZATION
        + _all_dimensions("\n    unobtanium_presence: 1.0\n")
        + _GOOD_CONFIDENCE,
    )
    with pytest.raises(DecisionKnowledgeError):
        load_knowledge(bad)


def test_negative_weight_raises(tmp_path):
    bad = _write(
        tmp_path / "k.yaml",
        'version: "1"\n'
        + _GOOD_NORMALIZATION
        + _all_dimensions("\n    repairability: -1.0\n")
        + _GOOD_CONFIDENCE,
    )
    with pytest.raises(DecisionKnowledgeError):
        load_knowledge(bad)


def test_all_zero_dimension_raises(tmp_path):
    bad = _write(
        tmp_path / "k.yaml",
        'version: "1"\n'
        + _GOOD_NORMALIZATION
        + _all_dimensions("\n    repairability: 0.0\n")
        + _GOOD_CONFIDENCE,
    )
    with pytest.raises(DecisionKnowledgeError):
        load_knowledge(bad)


def test_bool_weight_is_rejected_as_numeric(tmp_path):
    # ``True`` is an int subclass in Python; the loader must not accept it.
    bad = _write(
        tmp_path / "k.yaml",
        'version: "1"\n'
        + _GOOD_NORMALIZATION
        + _all_dimensions("\n    repairability: true\n")
        + _GOOD_CONFIDENCE,
    )
    with pytest.raises(DecisionKnowledgeError):
        load_knowledge(bad)


def test_unknown_confidence_source_raises(tmp_path):
    bad = _write(
        tmp_path / "k.yaml",
        'version: "1"\n'
        + _GOOD_NORMALIZATION
        + _all_dimensions()
        + "confidence:\n  clairvoyance: 1.0\n",
    )
    with pytest.raises(DecisionKnowledgeError):
        load_knowledge(bad)


def test_all_zero_confidence_raises(tmp_path):
    bad = _write(
        tmp_path / "k.yaml",
        'version: "1"\n'
        + _GOOD_NORMALIZATION
        + _all_dimensions()
        + "confidence:\n  materials: 0.0\n",
    )
    with pytest.raises(DecisionKnowledgeError):
        load_knowledge(bad)


def test_missing_confidence_raises(tmp_path):
    bad = _write(
        tmp_path / "k.yaml",
        'version: "1"\n' + _GOOD_NORMALIZATION + _all_dimensions(),
    )
    with pytest.raises(DecisionKnowledgeError):
        load_knowledge(bad)


# --- JSON catalogue parity ------------------------------------------------


def test_json_catalogue_loads(tmp_path):
    doc = {
        "version": "9.9.9",
        "normalization": {
            "carbon_saturation_kg": 100.0,
            "energy_saturation_mj": 1500.0,
            "water_saturation_l": 1000.0,
            "critical_recovery_saturation_kg": 0.05,
        },
        "dimensions": {
            dimension: {"repairability": 1.0}
            for dimension in DecisionDimension.values()
        },
        "confidence": {"materials": 1.0},
    }
    path = tmp_path / "k.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    knowledge = load_knowledge(path)
    assert knowledge.version == "9.9.9"
    assert set(knowledge.dimensions) == set(DecisionDimension)


# --- from_settings mapping ------------------------------------------------


def test_config_from_settings_maps_env_knobs():
    from device_ai.configs.settings import Settings
    from device_ai.decision.config import DecisionConfig

    settings = Settings(
        decision_knowledge_path="custom/knowledge.yaml",
        decision_min_confidence=0.2,
    )
    config = DecisionConfig.from_settings(settings)
    assert config.knowledge_path == "custom/knowledge.yaml"
    assert config.min_confidence == 0.2
