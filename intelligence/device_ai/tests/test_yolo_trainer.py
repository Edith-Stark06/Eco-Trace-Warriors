"""Unit tests for :class:`YOLOTrainer` (milestone M1.4).

The trainer delegates the epoch loop to Ultralytics, so these tests inject a
fake ``yolo_factory`` producing a fake model whose ``train``/``val``/``export``
mimic the Ultralytics surface. This exercises the whole ``fit`` delegation —
tracked run, checkpoint copy, ONNX export, model-registry registration and the
returned :class:`TrainingHistory` — with no torch/Ultralytics/GPU.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from device_ai.configs.settings import Settings
from device_ai.exceptions import TrainingError
from device_ai.training.config import OptimizerConfig, RunConfig, TrainingConfig
from device_ai.training.core.registry import default_registry
from device_ai.training.detector.yolo_trainer import YOLOTrainer
from device_ai.training.registry.model_registry import ModelRegistry


class _FakeConfusion:
    def __init__(self, matrix: list[list[float]]) -> None:
        self.matrix = matrix


class _FakeResults:
    """Stand-in for the object returned by ``model.train()`` / ``model.val()``."""

    def __init__(self, save_dir: Path) -> None:
        self.save_dir = str(save_dir)
        self.results_dict = {
            "metrics/precision(B)": 0.82,
            "metrics/recall(B)": 0.70,
            "metrics/mAP50(B)": 0.75,
            "metrics/mAP50-95(B)": 0.55,
        }
        self.confusion_matrix = _FakeConfusion([[5, 0], [1, 4]])


class _FakeTrainerHandle:
    """Stand-in for ``model.trainer`` exposing a resolved ``best`` path."""

    def __init__(self, best: Path) -> None:
        self.best = str(best)


class _FakeYolo:
    """A fake Ultralytics ``YOLO`` model recording its train/export calls."""

    def __init__(self, base_weights: str, *, save_root: Path) -> None:
        self.base_weights = base_weights
        self._save_root = save_root
        self.train_kwargs: dict[str, object] = {}
        self.export_kwargs: dict[str, object] = {}
        self.trainer: _FakeTrainerHandle | None = None

    def train(self, **kwargs: object) -> _FakeResults:
        """Record args, create a fake best.pt, and return canned results."""
        self.train_kwargs = kwargs
        save_dir = self._save_root / "run"
        weights = save_dir / "weights"
        weights.mkdir(parents=True, exist_ok=True)
        best = weights / "best.pt"
        best.write_text("trained-weights", encoding="utf-8")
        self.trainer = _FakeTrainerHandle(best)
        return _FakeResults(save_dir)

    def export(self, **kwargs: object) -> str:
        """Record args, write a fake ONNX file and return its path."""
        self.export_kwargs = kwargs
        onnx = self._save_root / "exported.onnx"
        onnx.write_text("onnx-bytes", encoding="utf-8")
        return str(onnx)


@pytest.fixture()
def detector_settings(tmp_path: Path) -> Settings:
    """Settings whose artifact/mlruns roots are isolated temp dirs."""
    return Settings(
        environment="development",
        log_level="WARNING",
        json_logs=False,
        artifact_dir=tmp_path / "artifacts",
        mlruns_dir=tmp_path / "mlruns",
        experiment_tracker="json",
        detector_weights="yolov8n.pt",
    )


@pytest.fixture()
def detector_run_config() -> RunConfig:
    """A small YOLO run config."""
    return RunConfig(
        model_name="device-detector",
        trainer="yolo",
        experiment_name="test-detection",
        training=TrainingConfig(
            epochs=5,
            batch_size=8,
            seed=7,
            device="cpu",
            image_size=320,
            model_version="1.0.0",
            early_stopping_patience=20,
        ),
        optimizer=OptimizerConfig(learning_rate=0.01),
        tags={"suite": "unit"},
    )


def _make_trainer(
    config: RunConfig,
    settings: Settings,
    save_root: Path,
    **kwargs: object,
) -> tuple[YOLOTrainer, list[_FakeYolo]]:
    """Build a trainer whose factory records the fake models it creates."""
    created: list[_FakeYolo] = []

    def factory(base_weights: str) -> _FakeYolo:
        model = _FakeYolo(base_weights, save_root=save_root)
        created.append(model)
        return model

    trainer = YOLOTrainer(
        config,
        settings,
        yolo_factory=factory,
        clock=lambda: datetime(2026, 1, 2, 3, 4, 5),
        commit="abc1234",
        **kwargs,
    )
    return trainer, created


def test_yolo_registered_in_default_registry() -> None:
    """Importing the trainer registers it under the ``yolo`` key."""
    assert "yolo" in default_registry
    assert default_registry.get("yolo") is YOLOTrainer


def test_fit_requires_data_config(
    detector_run_config: RunConfig, detector_settings: Settings, tmp_path: Path
) -> None:
    """A real fit without a data_config raises a TrainingError."""
    trainer, _ = _make_trainer(detector_run_config, detector_settings, tmp_path)
    with pytest.raises(TrainingError):
        trainer.fit()


def test_build_model_without_backend_or_factory_raises(
    detector_run_config: RunConfig, detector_settings: Settings
) -> None:
    """With no factory and no Ultralytics installed, build_model raises."""
    trainer = YOLOTrainer(detector_run_config, detector_settings)
    with pytest.raises(TrainingError):
        trainer.build_model()


def test_fit_delegates_and_records_provenance(
    detector_run_config: RunConfig,
    detector_settings: Settings,
    tmp_path: Path,
) -> None:
    """A full fit trains, checkpoints, exports, registers and returns history."""
    data_config = tmp_path / "data.yaml"
    data_config.write_text("path: .\ntrain: images\nval: images\n", encoding="utf-8")
    trainer, created = _make_trainer(
        detector_run_config,
        detector_settings,
        tmp_path,
        data_config=data_config,
    )

    history = trainer.fit()

    # The model was constructed from the configured base weights.
    assert len(created) == 1
    assert created[0].base_weights == "yolov8n.pt"

    # train() received the platform-resolved arguments.
    train_kwargs = created[0].train_kwargs
    assert train_kwargs["data"] == str(data_config)
    assert train_kwargs["epochs"] == 5
    assert train_kwargs["imgsz"] == 320
    assert train_kwargs["batch"] == 8
    assert train_kwargs["patience"] == 20
    assert train_kwargs["resume"] is False

    # The best checkpoint was copied into the artifact tree.
    checkpoint = Path(history.checkpoint_path)
    assert checkpoint.exists()
    assert checkpoint.read_text(encoding="utf-8") == "trained-weights"

    # History carries the mAP50-95 as the monitored best metric.
    assert history.final_metrics["mAP50_95"] == 0.55
    assert history.best_metric == 0.55
    assert history.git_commit == "abc1234"
    assert history.epochs_completed == 5

    # A provenance record was registered including the ONNX export format.
    registry = ModelRegistry.from_settings(detector_settings)
    record = registry.get("device-detector", "1.0.0")
    assert record.framework == "ultralytics"
    assert "onnx" in record.export_formats
    assert record.metrics["mAP50_95"] == 0.55


def test_fit_exports_onnx_into_artifact_tree(
    detector_run_config: RunConfig,
    detector_settings: Settings,
    tmp_path: Path,
) -> None:
    """The ONNX export is relocated under the managed exports directory."""
    data_config = tmp_path / "data.yaml"
    data_config.write_text("path: .\n", encoding="utf-8")
    trainer, _ = _make_trainer(
        detector_run_config, detector_settings, tmp_path, data_config=data_config
    )

    trainer.fit()

    exports_dir = Path(detector_settings.artifact_dir) / "exports"
    exported = exports_dir / "device-detector-1.0.0.onnx"
    assert exported.exists()
    assert exported.read_text(encoding="utf-8") == "onnx-bytes"


def test_fit_can_disable_export(
    detector_run_config: RunConfig,
    detector_settings: Settings,
    tmp_path: Path,
) -> None:
    """With export disabled, no ONNX format is recorded on the model record."""
    data_config = tmp_path / "data.yaml"
    data_config.write_text("path: .\n", encoding="utf-8")
    trainer, _ = _make_trainer(
        detector_run_config,
        detector_settings,
        tmp_path,
        data_config=data_config,
        export_onnx=False,
    )

    trainer.fit()

    registry = ModelRegistry.from_settings(detector_settings)
    record = registry.get("device-detector", "1.0.0")
    assert record.export_formats == ()


def test_fit_writes_tracked_run(
    detector_run_config: RunConfig,
    detector_settings: Settings,
    tmp_path: Path,
) -> None:
    """The JSON tracker records metrics and a summary for the run."""
    data_config = tmp_path / "data.yaml"
    data_config.write_text("path: .\n", encoding="utf-8")
    trainer, _ = _make_trainer(
        detector_run_config, detector_settings, tmp_path, data_config=data_config
    )

    history = trainer.fit()

    run_dir = Path(detector_settings.mlruns_dir) / history.run_id
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics[0]["mAP50_95"] == 0.55
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["summary"]["git_commit"] == "abc1234"
    assert "onnx" in meta["summary"]["export_formats"]


def test_resume_requested_via_tag(detector_settings: Settings, tmp_path: Path) -> None:
    """A ``resume: 'true'`` tag flows through to the Ultralytics train call."""
    config = RunConfig(
        model_name="device-detector",
        trainer="yolo",
        training=TrainingConfig(epochs=2, device="cpu", model_version="1.0.0"),
        tags={"resume": "true"},
    )
    data_config = tmp_path / "data.yaml"
    data_config.write_text("path: .\n", encoding="utf-8")
    trainer, created = _make_trainer(
        config, detector_settings, tmp_path, data_config=data_config
    )

    trainer.fit()

    assert created[0].train_kwargs["resume"] is True
