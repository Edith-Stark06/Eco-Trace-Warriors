"""Tests for the trainer registry, model registry and artifact manager (M1.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from device_ai.configs.settings import ARTIFACT_SUBDIRS, Settings
from device_ai.exceptions import (
    ModelNotFoundError,
    ModelRegistryError,
    TrainerNotFoundError,
)
from device_ai.training.core.registry import TrainerRegistry
from device_ai.training.registry.artifact_manager import ArtifactManager
from device_ai.training.registry.model_registry import (
    ModelRecord,
    ModelRegistry,
    record_from_dict,
    record_to_dict,
)


class TestTrainerRegistry:
    def test_register_and_get(self) -> None:
        registry = TrainerRegistry()

        @registry.register("alpha")
        class Alpha:
            pass

        assert registry.get("alpha") is Alpha
        assert "alpha" in registry
        assert registry.names() == ("alpha",)
        assert len(registry) == 1

    def test_unknown_trainer_raises(self) -> None:
        registry = TrainerRegistry()
        with pytest.raises(TrainerNotFoundError, match="No trainer registered"):
            registry.get("ghost")

    def test_duplicate_registration_rejected(self) -> None:
        registry = TrainerRegistry()

        @registry.register("dup")
        class First:
            pass

        with pytest.raises(ValueError, match="already registered"):

            @registry.register("dup")
            class Second:
                pass

    def test_empty_name_rejected(self) -> None:
        registry = TrainerRegistry()
        with pytest.raises(ValueError, match="non-empty"):
            registry.register("   ")


def _record(name: str = "device-detector", version: str = "1.0.0") -> ModelRecord:
    return ModelRecord(
        name=name,
        version=version,
        dataset_version="v1",
        created_at="2026-08-01T00:00:00",
        git_commit="abc1234",
        framework="mock",
        metrics={"loss": 0.1},
        export_formats=("pytorch",),
        artifact_location="artifacts/checkpoints/device-detector-1.0.0.pt",
        tags={"k": "v"},
    )


class TestModelRegistry:
    def test_register_and_list(self, tmp_path: Path) -> None:
        registry = ModelRegistry(tmp_path / "model_registry.json")
        registry.register(_record())
        models = registry.list_models()
        assert len(models) == 1
        assert models[0].key == "device-detector:1.0.0"

    def test_persistence_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "model_registry.json"
        ModelRegistry(path).register(_record())
        # A fresh instance reads what the first wrote.
        reloaded = ModelRegistry(path).get("device-detector", "1.0.0")
        assert reloaded.metrics == {"loss": 0.1}
        assert reloaded.export_formats == ("pytorch",)

    def test_latest_and_versions(self, tmp_path: Path) -> None:
        registry = ModelRegistry(tmp_path / "reg.json")
        registry.register(_record(version="1.0.0"))
        registry.register(_record(version="2.0.0"))
        assert registry.latest("device-detector").version == "2.0.0"
        assert len(registry.versions("device-detector")) == 2
        assert registry.latest("absent") is None

    def test_resolve_latest_and_exact(self, tmp_path: Path) -> None:
        registry = ModelRegistry(tmp_path / "reg.json")
        registry.register(_record(version="1.0.0"))
        assert registry.resolve("device-detector").version == "1.0.0"
        assert registry.resolve("device-detector", "1.0.0").version == "1.0.0"

    def test_resolve_latest_missing_raises(self, tmp_path: Path) -> None:
        registry = ModelRegistry(tmp_path / "reg.json")
        with pytest.raises(ModelNotFoundError, match="No versions"):
            registry.resolve("absent")

    def test_get_missing_raises(self, tmp_path: Path) -> None:
        registry = ModelRegistry(tmp_path / "reg.json")
        with pytest.raises(ModelNotFoundError):
            registry.get("absent", "1.0.0")

    def test_empty_registry_lists_nothing(self, tmp_path: Path) -> None:
        assert ModelRegistry(tmp_path / "reg.json").list_models() == []

    def test_corrupt_file_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "reg.json"
        path.write_text("{ not json", encoding="utf-8")
        with pytest.raises(ModelRegistryError, match="Failed to read"):
            ModelRegistry(path).list_models()

    def test_non_list_root_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "reg.json"
        path.write_text('{"a": 1}', encoding="utf-8")
        with pytest.raises(ModelRegistryError, match="must be a list"):
            ModelRegistry(path).list_models()

    def test_from_settings(self, training_settings: Settings) -> None:
        registry = ModelRegistry.from_settings(training_settings)
        registry.register(_record())
        assert (training_settings.artifact_dir / "model_registry.json").exists()

    def test_record_dict_round_trip(self) -> None:
        record = _record()
        assert record_from_dict(record_to_dict(record)) == record

    def test_record_from_partial_dict(self) -> None:
        record = record_from_dict({"name": "m", "version": "1"})
        assert record.git_commit == "unknown"
        assert record.metrics == {}


class TestArtifactManager:
    def test_ensure_creates_tree(self, training_settings: Settings) -> None:
        manager = ArtifactManager.from_settings(training_settings).ensure()
        for name in ARTIFACT_SUBDIRS:
            assert (manager.root / name).is_dir()

    def test_named_subdir_and_unknown(self, training_settings: Settings) -> None:
        manager = ArtifactManager.from_settings(training_settings)
        assert manager.subdir("checkpoints") == manager.checkpoints
        with pytest.raises(ValueError, match="Unknown artifact"):
            manager.subdir("bogus")

    def test_path_builders(self, training_settings: Settings) -> None:
        manager = ArtifactManager.from_settings(training_settings)
        ckpt = manager.checkpoint_path("m", "1.0.0")
        export = manager.export_path("m", "1.0.0", ".onnx")
        report = manager.report_path("m", "1.0.0", ".html")
        assert ckpt.name == "m-1.0.0.pt"
        assert export.name == "m-1.0.0.onnx"
        assert report.name == "m-1.0.0.html"
        # The parent directories are created on demand.
        assert ckpt.parent.is_dir()
        assert export.parent.is_dir()
        assert report.parent.is_dir()

    def test_registry_file_property(self, training_settings: Settings) -> None:
        manager = ArtifactManager.from_settings(training_settings)
        assert manager.registry_file.name == "model_registry.json"

    def test_all_subdirs_order(self, training_settings: Settings) -> None:
        manager = ArtifactManager.from_settings(training_settings)
        assert tuple(p.name for p in manager.all_subdirs()) == ARTIFACT_SUBDIRS
