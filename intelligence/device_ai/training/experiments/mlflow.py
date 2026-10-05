"""Optional MLflow experiment-tracking adapter (milestone M1.3).

This module wraps `MLflow <https://mlflow.org>`_ behind the same
:class:`~device_ai.training.experiments.tracker.ExperimentTracker` /
``RunHandle`` shape used by the default JSON tracker. MLflow is an *optional*
model dependency (see ``requirements-models.txt``) and is imported behind a
guard: in the base environment :func:`build_mlflow_tracker` returns ``None`` so
:func:`~device_ai.training.experiments.tracker.build_tracker` can fall back to
JSON without error.

Because MLflow is never installed in the test/base environment, the bodies that
actually call into it are marked ``# pragma: no cover``; only the import guard
and the ``None`` fallback are exercised by the suite.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

from ...configs.settings import Settings

try:  # pragma: no cover - exercised only when the optional dep is installed
    import mlflow

    _MLFLOW_AVAILABLE = True
except ImportError:
    _MLFLOW_AVAILABLE = False


def mlflow_available() -> bool:
    """Return whether the optional ``mlflow`` backend is importable.

    Returns:
        ``True`` when MLflow is installed, ``False`` in the base environment.
    """
    return _MLFLOW_AVAILABLE


class _MlflowRun:  # pragma: no cover - requires the optional mlflow dependency
    """A run handle backed by an active MLflow run."""

    def __init__(
        self,
        *,
        run_id: str,
        experiment_name: str,
        config: dict[str, Any] | None,
    ) -> None:
        self._run_id = run_id
        self._experiment_name = experiment_name
        self._config = config or {}
        self._active: Any = None

    @property
    def run_id(self) -> str:
        """Return the unique identifier of this run."""
        return self._run_id

    def log_params(self, params: dict[str, Any]) -> None:
        """Log flattened hyper-parameters to the active MLflow run."""
        mlflow.log_params({key: str(value) for key, value in params.items()})

    def log_metrics(self, metrics: dict[str, float], *, step: int) -> None:
        """Log a step's scalar metrics to the active MLflow run."""
        mlflow.log_metrics(
            {key: float(value) for key, value in metrics.items()}, step=step
        )

    def set_summary(self, summary: dict[str, Any]) -> None:
        """Record summary values as MLflow tags."""
        mlflow.set_tags({key: str(value) for key, value in summary.items()})

    def __enter__(self) -> _MlflowRun:
        """Start the MLflow run and log the seeded params."""
        if self._experiment_name:
            mlflow.set_experiment(self._experiment_name)
        self._active = mlflow.start_run(run_name=self._run_id)
        if self._config:
            self.log_params(self._config)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """End the active MLflow run."""
        mlflow.end_run()


class MlflowExperimentTracker:  # pragma: no cover - requires optional mlflow
    """Experiment tracker delegating to MLflow.

    Args:
        tracking_uri: Optional MLflow tracking URI (e.g. a local ``mlruns``
            directory or a remote server). When empty MLflow's own default is
            used.
    """

    backend = "mlflow"

    def __init__(self, tracking_uri: str = "") -> None:
        self._tracking_uri = tracking_uri
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)

    def run(
        self,
        *,
        run_id: str,
        experiment_name: str = "",
        config: dict[str, Any] | None = None,
    ) -> _MlflowRun:
        """Open an MLflow-backed run handle."""
        return _MlflowRun(run_id=run_id, experiment_name=experiment_name, config=config)


def build_mlflow_tracker(settings: Settings) -> MlflowExperimentTracker | None:
    """Construct an MLflow tracker, or ``None`` when MLflow is unavailable.

    Args:
        settings: Application settings supplying ``mlruns_dir`` (used as the
            local tracking URI).

    Returns:
        A :class:`MlflowExperimentTracker`, or ``None`` if MLflow is not
        installed, letting the caller fall back to the JSON tracker.
    """
    if not _MLFLOW_AVAILABLE:
        return None
    return MlflowExperimentTracker(  # pragma: no cover - optional dependency
        tracking_uri=str(settings.mlruns_dir)
    )
