"""Tests for the BaseTrainer lifecycle via a MockTrainer (milestone M1.3)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from device_ai.configs.settings import Settings
from device_ai.training.core.trainer import BaseTrainer, TrainingHistory
from device_ai.training.registry.model_registry import ModelRegistry


def _fixed_clock() -> datetime:
    return datetime(2026, 8, 1, 12, 0, 0)


def _make_trainer(cls, config, settings, **kwargs):
    """Construct a trainer with an injected fixed clock and commit."""
    kwargs.setdefault("clock", _fixed_clock)
    kwargs.setdefault("commit", "abc1234")
    return cls(config, settings, **kwargs)


class TestFitLifecycle:
    def test_returns_history(
        self, mock_trainer_cls, run_config, training_settings: Settings
    ) -> None:
        trainer = _make_trainer(mock_trainer_cls, run_config, training_settings)
        history = trainer.fit()
        assert isinstance(history, TrainingHistory)
        assert history.model_name == "device-detector"
        assert history.model_version == "1.0.0"
        assert history.epochs_completed == 3
        assert history.run_id == "device-detector-1.0.0-20260801-120000"
        assert history.git_commit == "abc1234"
        assert history.device == "cpu"
        assert history.training_time >= 0.0
        assert len(history.epochs) == 3

    def test_writes_checkpoint(
        self, mock_trainer_cls, run_config, training_settings: Settings
    ) -> None:
        trainer = _make_trainer(mock_trainer_cls, run_config, training_settings)
        history = trainer.fit()
        checkpoint = Path(history.checkpoint_path)
        assert checkpoint.exists()
        assert checkpoint.read_text(encoding="utf-8").startswith("checkpoint:")

    def test_auto_registers_model(
        self, mock_trainer_cls, run_config, training_settings: Settings
    ) -> None:
        trainer = _make_trainer(mock_trainer_cls, run_config, training_settings)
        history = trainer.fit()
        registry = ModelRegistry.from_settings(training_settings)
        record = registry.get("device-detector", "1.0.0")
        assert record.framework == "mock"
        assert record.dataset_version == "latest"
        assert record.git_commit == "abc1234"
        assert record.tags == {"suite": "unit"}
        assert record.artifact_location == history.checkpoint_path
        assert "val_loss" in record.metrics

    def test_logs_run_to_json_tracker(
        self, mock_trainer_cls, run_config, training_settings: Settings
    ) -> None:
        trainer = _make_trainer(mock_trainer_cls, run_config, training_settings)
        history = trainer.fit()
        run_dir = training_settings.mlruns_dir / history.run_id
        assert run_dir.is_dir()
        metrics = json.loads((run_dir / "metrics.json").read_text())
        assert len(metrics) == 3  # one entry per epoch
        meta = json.loads((run_dir / "meta.json").read_text())
        assert meta["summary"]["git_commit"] == "abc1234"
        assert meta["summary"]["epochs_completed"] == 3

    def test_metrics_include_val_prefixed(
        self, mock_trainer_cls, run_config, training_settings: Settings
    ) -> None:
        trainer = _make_trainer(mock_trainer_cls, run_config, training_settings)
        history = trainer.fit()
        assert "loss" in history.final_metrics
        assert "val_loss" in history.final_metrics

    def test_determinism_across_runs(
        self, mock_trainer_cls, run_config, training_settings: Settings
    ) -> None:
        first = _make_trainer(mock_trainer_cls, run_config, training_settings).fit()
        second = _make_trainer(mock_trainer_cls, run_config, training_settings).fit()
        assert first.final_metrics == second.final_metrics


class TestEarlyStopping:
    def test_early_stopping_halts_run(
        self, mock_trainer_cls, training_settings: Settings
    ) -> None:
        from device_ai.training.config import RunConfig, TrainingConfig

        # Constant val_loss with patience=1 -> stop after two non-improving.
        config = RunConfig(
            model_name="m",
            training=TrainingConfig(
                epochs=50, seed=1, device="cpu", early_stopping_patience=1
            ),
        )

        class Flat(mock_trainer_cls):  # type: ignore[misc,valid-type]
            def validation_step(self, model, batch):
                return {"loss": 1.0}

        trainer = _make_trainer(Flat, config, training_settings)
        history = trainer.fit()
        assert history.epochs_completed < 50


class TestDefaultCollaborators:
    def test_built_from_settings_when_omitted(
        self, mock_trainer_cls, run_config, training_settings: Settings
    ) -> None:
        # No artifacts/tracker/registry injected -> all derived from settings.
        trainer = mock_trainer_cls(run_config, training_settings)
        history = trainer.fit()
        assert Path(history.checkpoint_path).exists()

    def test_base_trainer_is_abstract(
        self, run_config, training_settings: Settings
    ) -> None:
        # BaseTrainer declares abstract hooks and cannot be instantiated.
        assert BaseTrainer.__abstractmethods__
        with pytest.raises(TypeError):
            BaseTrainer(run_config, training_settings)  # type: ignore[abstract]
