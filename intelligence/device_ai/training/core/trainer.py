"""The reusable training lifecycle for the platform (milestone M1.3).

:class:`BaseTrainer` captures everything that is *common* to training any model
in the Device Intelligence Engine — seeding, the epoch loop, metric aggregation,
callback dispatch, experiment tracking, checkpointing and automatic
registration — while deferring the *model-specific* pieces to abstract hooks
(:meth:`~BaseTrainer.build_model`, :meth:`~BaseTrainer.train_step`,
:meth:`~BaseTrainer.validation_step`, :meth:`~BaseTrainer.train_loader`,
:meth:`~BaseTrainer.val_loader`). Future ``YOLOTrainer`` / ``CLIPTrainer`` /
``OCRTrainer`` subclasses implement only those hooks.

Consistent with the M1.3 scope, **no concrete trainer ships here** — this module
provides only the abstract lifecycle. A ``MockTrainer`` in the test-suite
implements the hooks to exercise :meth:`~BaseTrainer.fit` end to end.

All collaborators (artifact layout, experiment tracker, model registry) and the
sources of non-determinism (the clock and Git commit) are **injected**, so a run
is fully reproducible and unit-testable without touching the wall clock, the
filesystem root or any global state.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ...configs.settings import Settings
from ..config import RunConfig
from ..experiments.tracker import ExperimentTracker, build_tracker
from ..registry.artifact_manager import ArtifactManager
from ..registry.model_registry import ModelRecord, ModelRegistry
from ..utils.env import resolve_device
from ..utils.git_utils import git_commit_hash
from ..utils.seeding import seed_everything
from ..utils.timing import Timer
from .callbacks import (
    Callback,
    CallbackList,
    EarlyStopping,
    LoggingCallback,
    ModelCheckpoint,
    TrainerState,
)
from .metrics import MetricTracker


@dataclass(frozen=True, slots=True)
class EpochResult:
    """Aggregated metrics for a single completed epoch.

    Attributes:
        epoch: 0-based epoch index.
        metrics: Mapping of metric name → averaged value for the epoch.
    """

    epoch: int
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TrainingHistory:
    """The immutable outcome of a :meth:`BaseTrainer.fit` call.

    Attributes:
        model_name: Logical model name that was trained.
        model_version: Version tag stamped onto the produced artifact.
        run_id: Unique identifier of the tracked run.
        epochs_completed: Number of epochs actually run (≤ configured epochs
            when early stopping fires).
        training_time: Wall-clock training duration in seconds.
        best_epoch: Epoch index selected as best by checkpointing (or ``-1``).
        best_metric: Monitored metric value at ``best_epoch`` (or ``None``).
        final_metrics: Aggregated metrics of the last completed epoch.
        checkpoint_path: POSIX path of the written checkpoint.
        git_commit: Short Git commit the run was produced from.
        device: Resolved compute device string.
        epochs: Per-epoch aggregated metrics, in order.
    """

    model_name: str
    model_version: str
    run_id: str
    epochs_completed: int
    training_time: float
    best_epoch: int
    best_metric: float | None
    final_metrics: dict[str, float]
    checkpoint_path: str
    git_commit: str
    device: str
    epochs: tuple[EpochResult, ...] = ()


class BaseTrainer(ABC):
    """Abstract, framework-agnostic training lifecycle.

    Subclasses implement the five abstract hooks; :meth:`fit` orchestrates them
    into a reproducible, tracked, auto-registered run.

    Class attributes ``framework``, ``monitor_metric`` and ``monitor_mode`` let a
    subclass declare its framework identifier and which metric the default
    callbacks watch, without overriding any method.

    Args:
        config: The validated run configuration.
        settings: Application settings (source of the artifact/mlruns roots).
        artifacts: Artifact layout; built from ``settings`` when omitted.
        tracker: Experiment tracker; built from ``settings`` when omitted.
        registry: Model registry; built from ``settings`` when omitted.
        callbacks: Explicit callback list; sensible defaults are derived from
            ``config`` when omitted.
        clock: Zero-argument factory returning the "current" time, injected for
            reproducibility (defaults to :meth:`datetime.now`).
        commit: Git commit hash to record; resolved via Git when omitted.
    """

    #: Framework identifier stored on the produced model record.
    framework: str = "base"
    #: Metric the default callbacks monitor for early stopping/checkpointing.
    monitor_metric: str = "val_loss"
    #: ``"min"`` (lower is better) or ``"max"`` for the monitored metric.
    monitor_mode: str = "min"

    def __init__(
        self,
        config: RunConfig,
        settings: Settings,
        *,
        artifacts: ArtifactManager | None = None,
        tracker: ExperimentTracker | None = None,
        registry: ModelRegistry | None = None,
        callbacks: list[Callback] | None = None,
        clock: Callable[[], datetime] | None = None,
        commit: str | None = None,
    ) -> None:
        self.config = config
        self.settings = settings
        self.artifacts = artifacts or ArtifactManager.from_settings(settings)
        self.tracker = tracker or build_tracker(settings)
        self.registry = registry or ModelRegistry.from_settings(settings)
        self._clock = clock or datetime.now
        self._commit = commit
        self._callbacks = CallbackList(
            callbacks if callbacks is not None else self._default_callbacks()
        )

    # -- Abstract, model-specific hooks -----------------------------------

    @abstractmethod
    def build_model(self) -> Any:
        """Construct and return the (untrained) model object.

        Returns:
            The model to train; its type is entirely up to the subclass.
        """

    @abstractmethod
    def train_loader(self) -> Iterable[Any]:
        """Return an iterable of training batches for one epoch."""

    @abstractmethod
    def val_loader(self) -> Iterable[Any]:
        """Return an iterable of validation batches for one epoch."""

    @abstractmethod
    def train_step(self, model: Any, batch: Any) -> dict[str, float]:
        """Run one training step and return its scalar metrics.

        Args:
            model: The model returned by :meth:`build_model`.
            batch: One item yielded by :meth:`train_loader`.

        Returns:
            A mapping of metric name → value (must include a ``"loss"`` key by
            convention, though this is not enforced).
        """

    @abstractmethod
    def validation_step(self, model: Any, batch: Any) -> dict[str, float]:
        """Run one validation step and return its scalar metrics.

        Args:
            model: The model returned by :meth:`build_model`.
            batch: One item yielded by :meth:`val_loader`.

        Returns:
            A mapping of metric name → value (validation metrics are prefixed
            with ``"val_"`` when aggregated).
        """

    # -- Overridable lifecycle pieces -------------------------------------

    def save_checkpoint(self, model: Any, path: Path) -> None:
        """Persist a checkpoint for ``model`` at ``path``.

        The default writes a small text marker so the lifecycle produces a real
        artifact even in the base environment (no torch). Framework subclasses
        override this to serialise actual weights.

        Args:
            model: The trained model object.
            path: Destination checkpoint path.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"checkpoint:{self.config.model_name}:{self.config.training.model_version}",
            encoding="utf-8",
        )

    def _default_callbacks(self) -> list[Callback]:
        """Build the default callback set from the run configuration.

        Always includes checkpoint tracking and logging; adds early stopping
        when ``training.early_stopping_patience`` is positive.

        Returns:
            The default list of callbacks.
        """
        callbacks: list[Callback] = [
            ModelCheckpoint(monitor=self.monitor_metric, mode=self.monitor_mode),
            LoggingCallback(),
        ]
        patience = self.config.training.early_stopping_patience
        if patience > 0:
            callbacks.append(
                EarlyStopping(
                    monitor=self.monitor_metric,
                    mode=self.monitor_mode,
                    patience=patience,
                )
            )
        return callbacks

    # -- The concrete lifecycle -------------------------------------------

    def _run_id(self, created_at: datetime) -> str:
        """Derive a deterministic run identifier from the config and clock."""
        stamp = created_at.strftime("%Y%m%d-%H%M%S")
        return f"{self.config.model_name}-{self.config.training.model_version}-{stamp}"

    def _aggregate(
        self,
        model: Any,
        batches: Iterable[Any],
        step: Callable[[Any, Any], dict[str, float]],
    ) -> dict[str, float]:
        """Run ``step`` over every batch and return the averaged metrics.

        Args:
            model: The model to pass to each step.
            batches: The iterable of batches for this phase.
            step: Either :meth:`train_step` or :meth:`validation_step`.

        Returns:
            The per-metric averages across all batches (empty when no batches).
        """
        tracker = MetricTracker()
        for batch in batches:
            tracker.update_many(step(model, batch))
        return tracker.averages()

    def fit(self) -> TrainingHistory:
        """Execute the full training lifecycle and return its history.

        The lifecycle: seed RNGs → open a tracked run → for each epoch, aggregate
        training and validation metrics and dispatch callbacks (honouring early
        stopping) → write a checkpoint → auto-register a
        :class:`~device_ai.training.registry.model_registry.ModelRecord`.

        Returns:
            A :class:`TrainingHistory` describing the completed run.
        """
        created_at = self._clock()
        run_id = self._run_id(created_at)
        commit = self._commit if self._commit is not None else git_commit_hash()
        device = resolve_device(self.config.training.device)

        seed_everything(self.config.training.seed)
        model = self.build_model()

        state = TrainerState(epochs=self.config.training.epochs)
        timer = Timer("training").start()

        with self.tracker.run(
            run_id=run_id,
            experiment_name=self.config.experiment_name,
            config=self.config.to_dict(),
        ) as run:
            self._callbacks.on_train_begin(state)
            final_logs: dict[str, float] = {}
            for epoch in range(self.config.training.epochs):
                state.epoch = epoch
                self._callbacks.on_epoch_begin(state)

                logs = self._aggregate(model, self.train_loader(), self.train_step)
                val_logs = self._aggregate(
                    model, self.val_loader(), self.validation_step
                )
                for key, value in val_logs.items():
                    logs[f"val_{key}"] = value

                state.history.append(dict(logs))
                run.log_metrics(logs, step=epoch)
                self._callbacks.on_epoch_end(state, logs)
                final_logs = logs
                if state.stop_training:
                    break

            self._callbacks.on_train_end(state)
            training_time = timer.stop()

            checkpoint = self.artifacts.checkpoint_path(
                self.config.model_name, self.config.training.model_version
            )
            self.save_checkpoint(model, checkpoint)

            run.set_summary(
                {
                    "training_time": training_time,
                    "git_commit": commit,
                    "device": device,
                    "best_epoch": state.best_epoch,
                    "epochs_completed": len(state.history),
                }
            )

        record = ModelRecord(
            name=self.config.model_name,
            version=self.config.training.model_version,
            dataset_version=self.config.training.dataset_version,
            created_at=created_at.isoformat(),
            git_commit=commit,
            framework=self.framework,
            metrics=final_logs,
            export_formats=(),
            artifact_location=checkpoint.as_posix(),
            tags=dict(self.config.tags),
        )
        self.registry.register(record)

        return TrainingHistory(
            model_name=self.config.model_name,
            model_version=self.config.training.model_version,
            run_id=run_id,
            epochs_completed=len(state.history),
            training_time=training_time,
            best_epoch=state.best_epoch,
            best_metric=state.best_metric,
            final_metrics=final_logs,
            checkpoint_path=checkpoint.as_posix(),
            git_commit=commit,
            device=device,
            epochs=tuple(
                EpochResult(epoch=index, metrics=metrics)
                for index, metrics in enumerate(state.history)
            ),
        )
