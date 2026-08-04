"""Experiment tracking for the training platform (milestone M1.3).

An *experiment tracker* records the parameters, per-epoch metrics and final
metadata of a training run so runs are comparable and reproducible. The default
:class:`JsonExperimentTracker` needs no third-party service: it writes a small
directory of JSON files under ``MLRUNS_DIR`` — the same conceptual layout MLflow
uses — so tracking works in the base environment. :class:`NullTracker` disables
tracking entirely.

An optional MLflow adapter lives in
:mod:`device_ai.training.experiments.mlflow`; :func:`build_tracker` selects a
backend from :class:`~device_ai.configs.settings.Settings` and *falls back* to
JSON (with a logged warning) when ``experiment_tracker="mlflow"`` but MLflow is
not installed, so a run is never blocked by a missing optional dependency.

Trackers are used as context managers::

    with tracker.run(run_id="...", config=cfg.to_dict()) as run:
        run.log_metrics({"loss": 0.1}, step=0)
        run.set_summary({"training_time": 12.3})

Nothing here trains a model; a tracker only records what a run reports.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, runtime_checkable

from loguru import logger

from ...configs.settings import Settings


@runtime_checkable
class RunHandle(Protocol):
    """A live handle to one tracked run.

    Implementations receive hyper-parameters via :meth:`log_params`, per-epoch
    metrics via :meth:`log_metrics` and a final summary via :meth:`set_summary`,
    and are used as context managers so resources are flushed on exit.
    """

    @property
    def run_id(self) -> str:
        """Return the unique identifier of this run."""
        ...

    def log_params(self, params: dict[str, Any]) -> None:
        """Record the run's hyper-parameters (typically once)."""
        ...

    def log_metrics(self, metrics: dict[str, float], *, step: int) -> None:
        """Record a set of scalar metrics for a given step (epoch)."""
        ...

    def set_summary(self, summary: dict[str, Any]) -> None:
        """Record final, run-level summary values (e.g. training time)."""
        ...

    def __enter__(self) -> RunHandle:
        """Enter the run context."""
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Flush and close the run on context exit."""
        ...


@runtime_checkable
class ExperimentTracker(Protocol):
    """A backend that opens tracked runs.

    A tracker is the injected collaborator the trainer calls to open a
    :class:`RunHandle` for the lifetime of a ``fit()`` invocation.
    """

    @property
    def backend(self) -> str:
        """Return the active backend identifier (``"json"``/``"mlflow"``/…)."""
        ...

    def run(
        self,
        *,
        run_id: str,
        experiment_name: str = "",
        config: dict[str, Any] | None = None,
    ) -> RunHandle:
        """Open a run handle for a single training run."""
        ...


class _JsonRun:
    """A single JSON-backed run written under ``<mlruns>/<run_id>/``.

    Three files are maintained, mirroring MLflow's conceptual split:
    ``params.json`` (hyper-parameters), ``metrics.json`` (per-step history) and
    ``meta.json`` (run identity plus the final summary). Each write persists the
    whole file, so a partially-completed run still leaves valid JSON on disk.
    """

    def __init__(
        self,
        *,
        run_id: str,
        run_dir: Path,
        experiment_name: str,
        config: dict[str, Any] | None,
    ) -> None:
        self._run_id = run_id
        self._dir = run_dir
        self._experiment_name = experiment_name
        self._params: dict[str, Any] = {}
        self._metric_history: list[dict[str, Any]] = []
        self._summary: dict[str, Any] = {}
        if config is not None:
            self._params = dict(config)

    @property
    def run_id(self) -> str:
        """Return the unique identifier of this run."""
        return self._run_id

    def _write(self, name: str, payload: Any) -> None:
        """Serialise ``payload`` to ``<run_dir>/<name>`` as sorted JSON."""
        self._dir.mkdir(parents=True, exist_ok=True)
        (self._dir / name).write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )

    def _write_meta(self) -> None:
        """Persist the run's identity and current summary to ``meta.json``."""
        self._write(
            "meta.json",
            {
                "run_id": self._run_id,
                "experiment_name": self._experiment_name,
                "summary": self._summary,
            },
        )

    def log_params(self, params: dict[str, Any]) -> None:
        """Merge and persist the run's hyper-parameters.

        Args:
            params: Mapping of parameter name → value (nested values allowed).
        """
        self._params.update(params)
        self._write("params.json", self._params)

    def log_metrics(self, metrics: dict[str, float], *, step: int) -> None:
        """Append a step's metrics to the history and persist it.

        Args:
            metrics: Mapping of metric name → scalar value.
            step: The step (epoch) index the metrics belong to.
        """
        entry: dict[str, Any] = {"step": step}
        entry.update({key: float(value) for key, value in metrics.items()})
        self._metric_history.append(entry)
        self._write("metrics.json", self._metric_history)

    def set_summary(self, summary: dict[str, Any]) -> None:
        """Merge and persist final run-level summary values.

        Args:
            summary: Mapping of summary key → value (e.g. ``training_time``).
        """
        self._summary.update(summary)
        self._write_meta()

    def __enter__(self) -> _JsonRun:
        """Persist the initial params/meta and return the run."""
        self._write("params.json", self._params)
        self._write_meta()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Flush the final metrics and metadata (exceptions not suppressed)."""
        self._write("metrics.json", self._metric_history)
        self._write_meta()


class JsonExperimentTracker:
    """Default tracker writing one JSON run directory per run under MLRUNS_DIR.

    Args:
        mlruns_dir: Root directory beneath which per-run folders are created.
    """

    backend = "json"

    def __init__(self, mlruns_dir: Path) -> None:
        self._root = Path(mlruns_dir)

    @classmethod
    def from_settings(cls, settings: Settings) -> JsonExperimentTracker:
        """Build a tracker rooted at ``settings.mlruns_dir``.

        Args:
            settings: Application settings supplying ``mlruns_dir``.

        Returns:
            A :class:`JsonExperimentTracker`.
        """
        return cls(settings.mlruns_dir)

    @property
    def root(self) -> Path:
        """The root directory beneath which runs are written."""
        return self._root

    def run(
        self,
        *,
        run_id: str,
        experiment_name: str = "",
        config: dict[str, Any] | None = None,
    ) -> _JsonRun:
        """Open a JSON-backed run directory.

        Args:
            run_id: Unique run identifier (used as the directory name).
            experiment_name: Optional grouping label recorded in ``meta.json``.
            config: Optional hyper-parameter mapping seeded into ``params.json``.

        Returns:
            A :class:`_JsonRun` context manager.
        """
        return _JsonRun(
            run_id=run_id,
            run_dir=self._root / run_id,
            experiment_name=experiment_name,
            config=config,
        )


class _NullRun:
    """A no-op run handle that discards everything it is given."""

    def __init__(self, run_id: str) -> None:
        self._run_id = run_id

    @property
    def run_id(self) -> str:
        """Return the unique identifier of this run."""
        return self._run_id

    def log_params(self, params: dict[str, Any]) -> None:
        """Discard the supplied parameters."""

    def log_metrics(self, metrics: dict[str, float], *, step: int) -> None:
        """Discard the supplied metrics."""

    def set_summary(self, summary: dict[str, Any]) -> None:
        """Discard the supplied summary."""

    def __enter__(self) -> _NullRun:
        """Return this no-op run."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Do nothing on exit."""


class NullTracker:
    """A tracker that records nothing (``experiment_tracker="none"``)."""

    backend = "none"

    def run(
        self,
        *,
        run_id: str,
        experiment_name: str = "",
        config: dict[str, Any] | None = None,
    ) -> _NullRun:
        """Open a no-op run handle.

        Args:
            run_id: Unique run identifier (echoed back on the handle).
            experiment_name: Ignored.
            config: Ignored.

        Returns:
            A :class:`_NullRun` context manager.
        """
        return _NullRun(run_id)


def build_tracker(settings: Settings) -> ExperimentTracker:
    """Select and construct the experiment tracker named by ``settings``.

    The mapping is: ``"none"`` → :class:`NullTracker`; ``"mlflow"`` →
    :class:`~device_ai.training.experiments.mlflow.MlflowExperimentTracker` when
    MLflow is importable, otherwise a warning is logged and the JSON tracker is
    used; anything else (default ``"json"``) → :class:`JsonExperimentTracker`.

    Args:
        settings: Application settings supplying ``experiment_tracker`` and
            ``mlruns_dir``.

    Returns:
        A ready-to-use experiment tracker.
    """
    choice = settings.experiment_tracker
    if choice == "none":
        return NullTracker()
    if choice == "mlflow":
        from .mlflow import build_mlflow_tracker

        tracker = build_mlflow_tracker(settings)
        if tracker is not None:
            return tracker
        logger.warning(
            "experiment_tracker='mlflow' but MLflow is not installed; "
            "falling back to the JSON tracker."
        )
    return JsonExperimentTracker.from_settings(settings)
