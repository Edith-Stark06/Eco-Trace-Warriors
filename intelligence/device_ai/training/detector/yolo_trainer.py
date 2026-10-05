"""YOLO detector trainer delegating to Ultralytics (milestone M1.4).

:class:`YOLOTrainer` is the first *real* trainer to plug into the M1.3 training
platform. Rather than re-implement an epoch loop through
:class:`~device_ai.training.core.trainer.BaseTrainer`'s ``train_step`` /
``validation_step`` hooks — which would **duplicate** functionality Ultralytics
already provides (resume, early-stopping, checkpointing and native MLflow
logging) — it *overrides* :meth:`fit` to delegate the training loop to
Ultralytics' ``model.train(...)`` while still **reusing** the platform's
provenance and reporting surface:

* :class:`~device_ai.training.registry.artifact_manager.ArtifactManager` — the
  checkpoint / export directory layout.
* :class:`~device_ai.training.registry.model_registry.ModelRegistry` — automatic
  registration of a :class:`ModelRecord` capturing full provenance.
* the injected :class:`~device_ai.training.experiments.tracker.ExperimentTracker`
  — our JSON/MLflow run wrapper.
* :class:`~device_ai.training.core.exporter.ExportRecord` + the
  ``artifacts.exports`` layout — the ONNX export result value object.

The five abstract :class:`BaseTrainer` hooks are still implemented (the ABC
requires them) but are **not driven** because :meth:`fit` is overridden;
:meth:`train_loader`/:meth:`val_loader` return empty iterables and the step
hooks raise, documenting that the epoch loop is Ultralytics', not ours.

**Optional backend, honest failure.** ``ultralytics`` is a heavy optional
dependency. Loading YOLO is import-guarded and can be replaced with an injected
``yolo_factory`` so the whole ``fit`` delegation is unit-testable with a fake in
the base environment. When neither a factory nor the real backend is available a
:class:`~device_ai.exceptions.TrainingError` is raised — you cannot train
without a training backend, and the platform says so rather than faking a run.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from ...configs.settings import Settings
from ...exceptions import TrainingError
from ..config import RunConfig
from ..core.exporter import ExportRecord, SkippedExport
from ..core.registry import default_registry
from ..core.trainer import BaseTrainer, EpochResult, TrainingHistory
from ..experiments.tracker import ExperimentTracker
from ..registry.artifact_manager import ArtifactManager
from ..registry.model_registry import ModelRecord, ModelRegistry
from ..utils.env import resolve_device
from ..utils.git_utils import git_commit_hash
from ..utils.seeding import seed_everything
from ..utils.timing import Timer
from .evaluation import extract_metrics


def _import_yolo() -> Any | None:
    """Return the Ultralytics ``YOLO`` class, or ``None`` when unavailable."""
    try:  # pragma: no cover - ultralytics is not installed in the base env
        from ultralytics import YOLO
    except ImportError:
        return None
    return YOLO  # pragma: no cover


@default_registry.register("yolo")
class YOLOTrainer(BaseTrainer):
    """Train an Ultralytics YOLO detector, reusing the platform for provenance.

    Args:
        config: The validated run configuration.
        settings: Application settings (artifact roots + detector base weights).
        data_config: Path to a YOLO ``data.yaml`` describing the dataset
            (produced by the dataset pipeline's ``export`` in ``yolo`` format).
            Required for a real :meth:`fit`; may be omitted in tests that inject
            a fake ``yolo_factory`` ignoring it.
        yolo_factory: Callable mapping base-weights string → a model object
            exposing ``train``/``val``/``export``. Injected by tests; defaults
            to constructing a real ``ultralytics.YOLO`` when the backend exists.
        export_onnx: Whether :meth:`fit` attempts an ONNX export after training.
        artifacts: Artifact layout; built from ``settings`` when omitted.
        tracker: Experiment tracker; built from ``settings`` when omitted.
        registry: Model registry; built from ``settings`` when omitted.
        clock: Zero-argument time factory, injected for reproducibility.
        commit: Git commit hash to record; resolved via Git when omitted.
    """

    framework = "ultralytics"
    #: Detection is inherently validated, so the monitored metric is the COCO
    #: mAP@50-95 emitted by :func:`extract_metrics` (higher is better).
    monitor_metric = "mAP50_95"
    monitor_mode = "max"

    def __init__(
        self,
        config: RunConfig,
        settings: Settings,
        *,
        data_config: Path | None = None,
        yolo_factory: Callable[[str], Any] | None = None,
        export_onnx: bool = True,
        artifacts: ArtifactManager | None = None,
        tracker: ExperimentTracker | None = None,
        registry: ModelRegistry | None = None,
        clock: Callable[[], datetime] | None = None,
        commit: str | None = None,
    ) -> None:
        super().__init__(
            config,
            settings,
            artifacts=artifacts,
            tracker=tracker,
            registry=registry,
            clock=clock,
            commit=commit,
        )
        self._data_config = data_config
        self._yolo_factory = yolo_factory
        self._export_onnx = export_onnx

    # -- Abstract hooks (present for the ABC; the epoch loop is Ultralytics') --

    def build_model(self) -> Any:
        """Construct the YOLO model from the configured base weights.

        Uses the injected ``yolo_factory`` when provided (tests), otherwise the
        real ``ultralytics.YOLO`` constructor.

        Returns:
            The model object (real ``YOLO`` or an injected fake).

        Raises:
            TrainingError: If no factory is given and Ultralytics is absent.
        """
        base_weights = self.settings.detector_weights
        if self._yolo_factory is not None:
            return self._yolo_factory(base_weights)
        yolo_cls = _import_yolo()
        if yolo_cls is None:
            raise TrainingError(
                "Ultralytics is not installed; cannot train the YOLO detector. "
                "Install requirements-models.txt or inject a yolo_factory.",
                details={"base_weights": base_weights},
            )
        return yolo_cls(base_weights)  # pragma: no cover - requires ultralytics

    def train_loader(self) -> Iterable[Any]:
        """Unused: Ultralytics owns data loading (see :meth:`fit`)."""
        return ()

    def val_loader(self) -> Iterable[Any]:
        """Unused: Ultralytics owns data loading (see :meth:`fit`)."""
        return ()

    def train_step(self, model: Any, batch: Any) -> dict[str, float]:
        """Not driven: the training loop is delegated to Ultralytics."""
        raise NotImplementedError(
            "YOLOTrainer delegates the training loop to Ultralytics; "
            "train_step is never called."
        )

    def validation_step(self, model: Any, batch: Any) -> dict[str, float]:
        """Not driven: the validation loop is delegated to Ultralytics."""
        raise NotImplementedError(
            "YOLOTrainer delegates the validation loop to Ultralytics; "
            "validation_step is never called."
        )

    # -- The delegated lifecycle ------------------------------------------

    def fit(self) -> TrainingHistory:
        """Train via Ultralytics, reusing the platform for provenance.

        The lifecycle: seed → build model → open a tracked run → delegate the
        epoch loop to ``model.train(...)`` (resume/early-stop/checkpoint are
        Ultralytics-native) → copy the best checkpoint into the artifact tree →
        optionally export ONNX → auto-register a :class:`ModelRecord` → return a
        :class:`TrainingHistory` of the same shape :class:`BaseTrainer` returns.

        Returns:
            A :class:`TrainingHistory` describing the completed run.

        Raises:
            TrainingError: If no ``data_config`` is available for a real run, or
                the training backend is unavailable.
        """
        created_at = self._clock()
        run_id = self._run_id(created_at)
        commit = self._commit if self._commit is not None else git_commit_hash()
        device = resolve_device(self.config.training.device)

        seed_everything(self.config.training.seed)
        model = self.build_model()

        timer = Timer("yolo-training").start()
        with self.tracker.run(
            run_id=run_id,
            experiment_name=self.config.experiment_name,
            config=self.config.to_dict(),
        ) as run:
            results = self._train(model, run_id=run_id, device=device)
            metrics = extract_metrics(results)
            run.log_metrics(metrics, step=0)

            checkpoint = self.artifacts.checkpoint_path(
                self.config.model_name, self.config.training.model_version
            )
            self._store_checkpoint(model, results, destination=checkpoint)
            exports = self._export(model)

            training_time = timer.stop()
            run.set_summary(
                {
                    "training_time": training_time,
                    "git_commit": commit,
                    "device": device,
                    "export_formats": [e.export_format for e in exports if e.exported],
                }
            )

        export_formats = tuple(e.export_format for e in exports if e.exported)
        record = ModelRecord(
            name=self.config.model_name,
            version=self.config.training.model_version,
            dataset_version=self.config.training.dataset_version,
            created_at=created_at.isoformat(),
            git_commit=commit,
            framework=self.framework,
            metrics=metrics,
            export_formats=export_formats,
            artifact_location=checkpoint.as_posix(),
            tags=dict(self.config.tags),
        )
        self.registry.register(record)

        best_metric = metrics.get(self.monitor_metric)
        return TrainingHistory(
            model_name=self.config.model_name,
            model_version=self.config.training.model_version,
            run_id=run_id,
            epochs_completed=self.config.training.epochs,
            training_time=training_time,
            best_epoch=-1,
            best_metric=best_metric,
            final_metrics=metrics,
            checkpoint_path=checkpoint.as_posix(),
            git_commit=commit,
            device=device,
            epochs=(EpochResult(epoch=0, metrics=metrics),),
        )

    # -- Delegation helpers -----------------------------------------------

    def _train(self, model: Any, *, run_id: str, device: str) -> Any:
        """Invoke ``model.train(...)`` with platform-resolved arguments.

        Args:
            model: The model returned by :meth:`build_model`.
            run_id: Run identifier used as the Ultralytics run ``name``.
            device: Resolved compute device string.

        Returns:
            The Ultralytics training results object (or a fake's stand-in).

        Raises:
            TrainingError: If no ``data_config`` was supplied.
        """
        if self._data_config is None:
            raise TrainingError(
                "YOLOTrainer.fit requires a data_config (path to a YOLO "
                "data.yaml). Export a dataset in 'yolo' format first.",
                details={"model_name": self.config.model_name},
            )
        training = self.config.training
        resume = self._resume_requested()
        return model.train(
            data=str(self._data_config),
            epochs=training.epochs,
            imgsz=training.image_size,
            batch=training.batch_size,
            patience=training.early_stopping_patience,
            device=device,
            seed=training.seed,
            project=str(self.artifacts.checkpoints),
            name=run_id,
            resume=resume,
            verbose=False,
        )

    def _resume_requested(self) -> bool:
        """Return whether the run config requests resuming a prior run.

        Resume is opt-in via a ``resume: "true"`` run tag (there is no dedicated
        field on the frozen :class:`TrainingConfig`).

        Returns:
            ``True`` when resume is requested, ``False`` otherwise.
        """
        return str(self.config.tags.get("resume", "")).strip().lower() == "true"

    def _store_checkpoint(self, model: Any, results: Any, *, destination: Path) -> None:
        """Copy the best trained checkpoint into the artifact tree.

        Prefers Ultralytics' resolved ``best.pt``; when it cannot be located
        (e.g. a fake that trained no real weights) a small marker is written via
        :meth:`BaseTrainer.save_checkpoint` so the artifact location is always
        valid.

        Args:
            model: The trained model object.
            results: The training results object.
            destination: Target checkpoint path in the artifact tree.
        """
        source = self._resolve_best_weights(model, results)
        if source is not None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            logger.info("Stored detector checkpoint at '{}'.", destination)
            return
        logger.warning(
            "No trained weights located; writing a checkpoint marker at '{}'.",
            destination,
        )
        self.save_checkpoint(model, destination)

    @staticmethod
    def _resolve_best_weights(model: Any, results: Any) -> Path | None:
        """Locate the best-checkpoint file produced by Ultralytics.

        Args:
            model: The trained model object (its ``trainer.best`` is preferred).
            results: The training results object (its ``save_dir`` is a
                fallback: ``<save_dir>/weights/best.pt``).

        Returns:
            The best-weights path, or ``None`` when none exists on disk.
        """
        trainer = getattr(model, "trainer", None)
        best = getattr(trainer, "best", None) if trainer is not None else None
        if best:
            best_path = Path(best)
            if best_path.exists():
                return best_path
        save_dir = getattr(results, "save_dir", None)
        if save_dir:
            candidate = Path(save_dir) / "weights" / "best.pt"
            if candidate.exists():
                return candidate
        return None

    def _export(self, model: Any) -> list[ExportRecord]:
        """Export the trained model to ONNX via Ultralytics, when requested.

        Args:
            model: The trained model object exposing ``export(format=...)``.

        Returns:
            A list with one :class:`ExportRecord`; a skipped record when export
            is disabled, unsupported by the model, or fails.
        """
        if not self._export_onnx:
            return [SkippedExport("onnx", "ONNX export disabled for this run.")]
        exporter = getattr(model, "export", None)
        if not callable(exporter):
            return [SkippedExport("onnx", "Model does not support export().")]
        try:
            produced = exporter(format="onnx")
        except Exception as exc:  # noqa: BLE001 - degrade to a skipped record
            logger.warning("ONNX export failed: {}", exc)
            return [SkippedExport("onnx", f"ONNX export failed: {exc}")]
        location = self._relocate_export(produced, suffix=".onnx")
        return [
            ExportRecord(
                export_format="onnx",
                status="exported",
                location=location.as_posix(),
            )
        ]

    def _relocate_export(self, produced: Any, *, suffix: str) -> Path:
        """Move an exported artifact into the managed exports directory.

        Args:
            produced: The path (str/Path) Ultralytics reports for the export.
            suffix: The artifact file suffix (e.g. ``".onnx"``).

        Returns:
            The destination path inside ``artifacts.exports``. When the produced
            file is absent (a fake), the destination path is still returned
            (unwritten) so the record's location is stable.
        """
        destination = self.artifacts.export_path(
            self.config.model_name, self.config.training.model_version, suffix
        )
        source = Path(str(produced))
        if source.exists() and source != destination:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        return destination
