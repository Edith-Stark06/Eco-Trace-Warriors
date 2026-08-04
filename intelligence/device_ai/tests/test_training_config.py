"""Tests for the training run-configuration layer (milestone M1.3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from device_ai.exceptions import ConfigError
from device_ai.training.config import (
    OptimizerConfig,
    RunConfig,
    TrainingConfig,
    hydra_available,
    load_config,
)

DEFAULT_CONFIG = (
    Path(__file__).resolve().parents[1] / "training" / "configs" / "default.yaml"
)


def test_defaults_are_sensible() -> None:
    config = RunConfig()
    assert config.model_name == "device-detector"
    assert config.trainer == "mock"
    assert config.training.epochs == 100
    assert config.optimizer.learning_rate == pytest.approx(1e-3)


def test_configs_are_frozen() -> None:
    config = RunConfig()
    with pytest.raises(ValidationError):
        config.model_name = "other"  # type: ignore[misc]


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        TrainingConfig(unknown_field=1)  # type: ignore[call-arg]


def test_validation_bounds() -> None:
    with pytest.raises(ValidationError):
        TrainingConfig(epochs=0)
    with pytest.raises(ValidationError):
        OptimizerConfig(learning_rate=0.0)


def test_to_dict_round_trips() -> None:
    config = RunConfig(tags={"a": "b"})
    data = config.to_dict()
    assert data["tags"] == {"a": "b"}
    assert data["training"]["epochs"] == 100
    assert RunConfig.model_validate(data) == config


def test_hydra_available_is_false_in_base_env() -> None:
    assert hydra_available() is False


def test_load_packaged_default_config() -> None:
    config = load_config(DEFAULT_CONFIG)
    assert config.model_name == "device-detector"
    assert config.training.batch_size == 16
    assert config.optimizer.warmup_epochs == 3
    assert config.tags == {"milestone": "M1.3", "stage": "platform"}


def test_load_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_load_config_malformed_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("key: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="parse"):
        load_config(bad)


def test_load_config_non_mapping_root(tmp_path: Path) -> None:
    bad = tmp_path / "list.yaml"
    bad.write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(bad)


def test_empty_file_yields_defaults(tmp_path: Path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    config = load_config(empty)
    assert config == RunConfig()


def test_defaults_must_be_a_list(tmp_path: Path) -> None:
    bad = tmp_path / "cfg.yaml"
    bad.write_text("defaults: not-a-list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a list"):
        load_config(bad)


def test_defaults_entries_must_be_strings(tmp_path: Path) -> None:
    bad = tmp_path / "cfg.yaml"
    bad.write_text("defaults:\n  - 123\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="config-group name"):
        load_config(bad)


def test_compose_and_merge(tmp_path: Path) -> None:
    (tmp_path / "training.yaml").write_text(
        "epochs: 5\nbatch_size: 8\n", encoding="utf-8"
    )
    (tmp_path / "optimizer.yaml").write_text("learning_rate: 0.02\n", encoding="utf-8")
    (tmp_path / "run.yaml").write_text(
        "defaults:\n  - training\n  - optimizer\nmodel_name: custom\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path / "run.yaml")
    assert config.model_name == "custom"
    assert config.training.epochs == 5
    assert config.optimizer.learning_rate == pytest.approx(0.02)


def test_overrides_win(tmp_path: Path) -> None:
    (tmp_path / "training.yaml").write_text("epochs: 5\n", encoding="utf-8")
    (tmp_path / "run.yaml").write_text("defaults:\n  - training\n", encoding="utf-8")
    config = load_config(tmp_path / "run.yaml", overrides={"training": {"epochs": 42}})
    assert config.training.epochs == 42


def test_invalid_composed_config_raises(tmp_path: Path) -> None:
    (tmp_path / "training.yaml").write_text("epochs: -1\n", encoding="utf-8")
    (tmp_path / "run.yaml").write_text("defaults:\n  - training\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid training configuration"):
        load_config(tmp_path / "run.yaml")
