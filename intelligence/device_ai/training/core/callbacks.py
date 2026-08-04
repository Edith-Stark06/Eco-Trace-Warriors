"""Training callbacks for the training platform (milestone M1.3).

Callbacks let cross-cutting behaviour — early stopping, checkpoint selection,
logging — hook into the training loop without the trainer knowing about any of
them. Each concrete :class:`Callback` overrides only the lifecycle hooks it
cares about; :class:`CallbackList` fans a single event out to an ordered
collection of callbacks.

The hooks are framework-agnostic and receive a mutable ``logs`` mapping (the
current epoch's aggregated metrics). :class:`EarlyStopping` decides *when* to
stop by setting :attr:`TrainerState.stop_training`; the trainer owns the loop
and simply honours that flag. Nothing here touches a model's weights directly —
:class:`ModelCheckpoint` records *which* epoch was best so the trainer can
persist it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class TrainerState:
    """Mutable state shared between the trainer and its callbacks.

    A single instance is threaded through every callback hook of a run so
    callbacks can communicate with the trainer (and each other) without global
    state.

    Attributes:
        epoch: The current (0-based) epoch index.
        epochs: Total number of epochs the run will attempt.
        stop_training: When set ``True`` by a callback, the trainer breaks out
            of the epoch loop after the current epoch.
        best_metric: Best value observed so far of the monitored metric.
        best_epoch: Epoch index at which ``best_metric`` was observed.
        history: Per-epoch record of aggregated metric mappings.
    """

    epoch: int = 0
    epochs: int = 0
    stop_training: bool = False
    best_metric: float | None = None
    best_epoch: int = -1
    history: list[dict[str, float]] = field(default_factory=list)


class Callback:
    """Base class for training callbacks (all hooks default to no-ops).

    Subclasses override only the hooks they need. Every hook receives the shared
    :class:`TrainerState` and, where relevant, a mutable ``logs`` mapping of the
    epoch's aggregated metrics.
    """

    def on_train_begin(self, state: TrainerState) -> None:
        """Called once before the first epoch."""

    def on_train_end(self, state: TrainerState) -> None:
        """Called once after the final epoch (or early stop)."""

    def on_epoch_begin(self, state: TrainerState) -> None:
        """Called at the start of each epoch."""

    def on_epoch_end(self, state: TrainerState, logs: dict[str, float]) -> None:
        """Called at the end of each epoch with its aggregated metrics."""


class CallbackList:
    """Fan a single lifecycle event out to an ordered list of callbacks.

    Args:
        callbacks: The callbacks to dispatch to, in order. ``None`` yields an
            empty list.
    """

    def __init__(self, callbacks: list[Callback] | None = None) -> None:
        self._callbacks: list[Callback] = list(callbacks or [])

    def __len__(self) -> int:
        """Return the number of registered callbacks."""
        return len(self._callbacks)

    def __iter__(self) -> Any:
        """Iterate over the registered callbacks in order."""
        return iter(self._callbacks)

    def append(self, callback: Callback) -> None:
        """Add a callback to the end of the list.

        Args:
            callback: The callback to register.
        """
        self._callbacks.append(callback)

    def on_train_begin(self, state: TrainerState) -> None:
        """Dispatch ``on_train_begin`` to every callback."""
        for callback in self._callbacks:
            callback.on_train_begin(state)

    def on_train_end(self, state: TrainerState) -> None:
        """Dispatch ``on_train_end`` to every callback."""
        for callback in self._callbacks:
            callback.on_train_end(state)

    def on_epoch_begin(self, state: TrainerState) -> None:
        """Dispatch ``on_epoch_begin`` to every callback."""
        for callback in self._callbacks:
            callback.on_epoch_begin(state)

    def on_epoch_end(self, state: TrainerState, logs: dict[str, float]) -> None:
        """Dispatch ``on_epoch_end`` to every callback."""
        for callback in self._callbacks:
            callback.on_epoch_end(state, logs)


def _is_improvement(
    current: float, best: float, *, mode: str, min_delta: float
) -> bool:
    """Return whether ``current`` improves on ``best`` under ``mode``.

    Args:
        current: The freshly observed monitored value.
        best: The best value observed so far.
        mode: ``"min"`` (lower is better) or ``"max"`` (higher is better).
        min_delta: Minimum change to qualify as an improvement.

    Returns:
        ``True`` when ``current`` is a qualifying improvement over ``best``.
    """
    if mode == "min":
        return current < best - min_delta
    return current > best + min_delta


class EarlyStopping(Callback):
    """Stop training when a monitored metric stops improving.

    Args:
        monitor: Name of the metric to watch in the epoch ``logs``.
        patience: Number of epochs with no improvement to tolerate before
            stopping. ``0`` still stops on the first non-improving epoch.
        mode: ``"min"`` (lower is better, e.g. loss) or ``"max"`` (higher is
            better, e.g. accuracy).
        min_delta: Minimum change in the monitored value to count as an
            improvement.

    Raises:
        ValueError: If ``mode`` is not ``"min"`` or ``"max"``, or ``patience``
            is negative.
    """

    def __init__(
        self,
        *,
        monitor: str = "val_loss",
        patience: int = 5,
        mode: str = "min",
        min_delta: float = 0.0,
    ) -> None:
        if mode not in ("min", "max"):
            raise ValueError(f"mode must be 'min' or 'max', got {mode!r}")
        if patience < 0:
            raise ValueError(f"patience must be non-negative, got {patience}")
        self.monitor = monitor
        self.patience = patience
        self.mode = mode
        self.min_delta = min_delta
        self._best: float | None = None
        self._wait = 0

    @property
    def best(self) -> float | None:
        """The best monitored value observed so far (``None`` before any)."""
        return self._best

    def on_train_begin(self, state: TrainerState) -> None:
        """Reset the internal best/wait counters for a fresh run."""
        self._best = None
        self._wait = 0

    def on_epoch_end(self, state: TrainerState, logs: dict[str, float]) -> None:
        """Update the wait counter and request a stop when patience is exceeded.

        The monitored metric is read from ``logs``; a missing metric is ignored
        (no decision is made that epoch).
        """
        if self.monitor not in logs:
            return
        current = logs[self.monitor]
        if self._best is None or _is_improvement(
            current, self._best, mode=self.mode, min_delta=self.min_delta
        ):
            self._best = current
            self._wait = 0
            return
        self._wait += 1
        if self._wait > self.patience:
            state.stop_training = True


class ModelCheckpoint(Callback):
    """Track which epoch produced the best monitored metric.

    The callback does not write weights itself (the trainer owns persistence);
    it records the best epoch and value on the shared :class:`TrainerState` so
    the trainer can checkpoint the right epoch. ``save_best_only`` mirrors the
    familiar Keras flag for future weight-writing trainers.

    Args:
        monitor: Metric to watch in the epoch ``logs``.
        mode: ``"min"`` or ``"max"`` (see :class:`EarlyStopping`).
        save_best_only: Whether only improvements should be considered
            checkpoint-worthy (advisory; recorded for the trainer).

    Raises:
        ValueError: If ``mode`` is not ``"min"`` or ``"max"``.
    """

    def __init__(
        self,
        *,
        monitor: str = "val_loss",
        mode: str = "min",
        save_best_only: bool = True,
    ) -> None:
        if mode not in ("min", "max"):
            raise ValueError(f"mode must be 'min' or 'max', got {mode!r}")
        self.monitor = monitor
        self.mode = mode
        self.save_best_only = save_best_only
        self._best: float | None = None
        self.best_epoch: int = -1

    @property
    def best(self) -> float | None:
        """The best monitored value observed so far (``None`` before any)."""
        return self._best

    def on_train_begin(self, state: TrainerState) -> None:
        """Reset the recorded best value/epoch for a fresh run."""
        self._best = None
        self.best_epoch = -1

    def on_epoch_end(self, state: TrainerState, logs: dict[str, float]) -> None:
        """Record the epoch as best when the monitored metric improves."""
        if self.monitor not in logs:
            return
        current = logs[self.monitor]
        improved = self._best is None or _is_improvement(
            current, self._best, mode=self.mode, min_delta=0.0
        )
        if improved or not self.save_best_only:
            self._best = current
            self.best_epoch = state.epoch
            state.best_metric = current
            state.best_epoch = state.epoch


class LoggingCallback(Callback):
    """Log a concise one-line summary of each epoch via Loguru.

    Args:
        every_n_epochs: Emit a log line every ``n`` epochs (and always on the
            final epoch). Must be at least 1.

    Raises:
        ValueError: If ``every_n_epochs`` is less than 1.
    """

    def __init__(self, *, every_n_epochs: int = 1) -> None:
        if every_n_epochs < 1:
            raise ValueError(f"every_n_epochs must be >= 1, got {every_n_epochs}")
        self.every_n_epochs = every_n_epochs

    def on_train_begin(self, state: TrainerState) -> None:
        """Log the start of training."""
        logger.info("Training started for {} epoch(s).", state.epochs)

    def on_epoch_end(self, state: TrainerState, logs: dict[str, float]) -> None:
        """Log the epoch's metrics on the configured cadence."""
        is_last = state.epoch + 1 >= state.epochs
        if (state.epoch + 1) % self.every_n_epochs != 0 and not is_last:
            return
        metrics = ", ".join(f"{key}={value:.4f}" for key, value in logs.items())
        logger.info("Epoch {}/{} — {}", state.epoch + 1, state.epochs, metrics)

    def on_train_end(self, state: TrainerState) -> None:
        """Log the end of training and the best observed epoch."""
        if state.best_epoch >= 0:
            logger.info(
                "Training finished. Best epoch: {} (metric={:.4f}).",
                state.best_epoch + 1,
                state.best_metric if state.best_metric is not None else float("nan"),
            )
        else:
            logger.info("Training finished after {} epoch(s).", len(state.history))
