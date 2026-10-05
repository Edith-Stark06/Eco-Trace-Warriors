"""Tests for the training-platform CLIs (milestone M1.3)."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from device_ai.configs.settings import Settings
from device_ai.training.cli import (
    default_config_path,
    evaluate_main,
    export_main,
    train_main,
)
from device_ai.training.core.registry import TrainerRegistry
from device_ai.training.registry.model_registry import ModelRecord, ModelRegistry


def test_default_config_path_exists() -> None:
    assert default_config_path().exists()


class TestTrainCli:
    def test_dry_run_prints_plan(
        self, training_settings: Settings, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = train_main(
            ["--epochs", "7", "--model-name", "device-detector"],
            settings=training_settings,
        )
        assert code == 0
        plan = json.loads(capsys.readouterr().out)
        assert plan["epochs"] == 7
        assert plan["model_name"] == "device-detector"
        assert plan["hydra_available"] is False
        # Dry run must not train: no run directory, no registry entry.
        assert not training_settings.mlruns_dir.exists() or not any(
            training_settings.mlruns_dir.glob("*/meta.json")
        )

    def test_all_overrides_applied(
        self, training_settings: Settings, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = train_main(
            [
                "--epochs",
                "3",
                "--batch-size",
                "8",
                "--device",
                "cpu",
                "--model-version",
                "2.0.0",
                "--model-name",
                "custom-model",
                "--trainer",
                "mock",
            ],
            settings=training_settings,
        )
        assert code == 0
        plan = json.loads(capsys.readouterr().out)
        assert plan["batch_size"] == 8
        assert plan["device"] == "cpu"
        assert plan["model_version"] == "2.0.0"
        assert plan["model_name"] == "custom-model"
        assert plan["trainer"] == "mock"

    def test_run_with_registered_trainer(
        self, training_settings: Settings, mock_trainer_cls
    ) -> None:
        registry = TrainerRegistry()
        registry.register("mock")(mock_trainer_cls)
        code = train_main(
            ["--run", "--trainer", "mock", "--epochs", "2"],
            settings=training_settings,
            registry=registry,
        )
        assert code == 0
        models = ModelRegistry.from_settings(training_settings).list_models()
        assert len(models) == 1

    def test_run_without_registered_trainer_fails(
        self, training_settings: Settings
    ) -> None:
        code = train_main(
            ["--run", "--trainer", "ghost"],
            settings=training_settings,
            registry=TrainerRegistry(),
        )
        assert code == 1


def _register_model(settings: Settings) -> None:
    ModelRegistry.from_settings(settings).register(
        ModelRecord(
            name="device-detector",
            version="1.0.0",
            dataset_version="v1",
            created_at="2026-08-01T00:00:00",
            git_commit="abc1234",
            framework="mock",
            metrics={"accuracy": 0.9, "loss": 0.1},
        )
    )


class TestEvaluateCli:
    def test_writes_reports(self, training_settings: Settings) -> None:
        _register_model(training_settings)
        code = evaluate_main(
            ["--model-name", "device-detector"],
            settings=training_settings,
            clock=lambda: datetime(2026, 8, 1),
        )
        assert code == 0
        reports = training_settings.artifact_dir / "reports"
        json_report = reports / "device-detector-1.0.0.json"
        html_report = reports / "device-detector-1.0.0.html"
        assert json_report.exists()
        assert html_report.exists()
        document = json.loads(json_report.read_text())
        assert document["metrics"]["accuracy"] == 0.9
        assert "<script" not in html_report.read_text().lower()

    def test_unknown_model_fails(self, training_settings: Settings) -> None:
        code = evaluate_main(["--model-name", "ghost"], settings=training_settings)
        assert code == 1


class TestExportCli:
    def test_exports_are_skipped_without_torch(
        self, training_settings: Settings
    ) -> None:
        _register_model(training_settings)
        code = export_main(
            ["--model-name", "device-detector"], settings=training_settings
        )
        assert code == 0  # skips are a success, not a failure

    def test_custom_formats(self, training_settings: Settings) -> None:
        _register_model(training_settings)
        code = export_main(
            ["--model-name", "device-detector", "--formats", "onnx"],
            settings=training_settings,
        )
        assert code == 0

    def test_unknown_model_fails(self, training_settings: Settings) -> None:
        code = export_main(["--model-name", "ghost"], settings=training_settings)
        assert code == 1
