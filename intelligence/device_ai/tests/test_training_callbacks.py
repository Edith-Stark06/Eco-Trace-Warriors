"""Tests for training callbacks (milestone M1.3)."""

from __future__ import annotations

import pytest

from device_ai.training.core.callbacks import (
    Callback,
    CallbackList,
    EarlyStopping,
    LoggingCallback,
    ModelCheckpoint,
    TrainerState,
)


def _run_epochs(
    callback: Callback, values: list[float], *, metric: str
) -> TrainerState:
    """Drive a callback through a sequence of epoch metric values."""
    state = TrainerState(epochs=len(values))
    callback.on_train_begin(state)
    for epoch, value in enumerate(values):
        state.epoch = epoch
        callback.on_epoch_end(state, {metric: value})
        if state.stop_training:
            break
    callback.on_train_end(state)
    return state


class TestCallbackList:
    def test_dispatches_to_all(self) -> None:
        events: list[str] = []

        class Recorder(Callback):
            def __init__(self, tag: str) -> None:
                self.tag = tag

            def on_train_begin(self, state: TrainerState) -> None:
                events.append(f"begin-{self.tag}")

            def on_epoch_begin(self, state: TrainerState) -> None:
                events.append(f"epoch-begin-{self.tag}")

            def on_epoch_end(self, state: TrainerState, logs: dict) -> None:
                events.append(f"epoch-end-{self.tag}")

            def on_train_end(self, state: TrainerState) -> None:
                events.append(f"end-{self.tag}")

        callbacks = CallbackList([Recorder("a")])
        callbacks.append(Recorder("b"))
        state = TrainerState(epochs=1)
        callbacks.on_train_begin(state)
        callbacks.on_epoch_begin(state)
        callbacks.on_epoch_end(state, {})
        callbacks.on_train_end(state)
        assert len(callbacks) == 2
        assert list(callbacks)  # iterable
        assert events == [
            "begin-a",
            "begin-b",
            "epoch-begin-a",
            "epoch-begin-b",
            "epoch-end-a",
            "epoch-end-b",
            "end-a",
            "end-b",
        ]

    def test_base_callback_hooks_are_noops(self) -> None:
        state = TrainerState()
        callback = Callback()
        callback.on_train_begin(state)
        callback.on_epoch_begin(state)
        callback.on_epoch_end(state, {})
        callback.on_train_end(state)  # must not raise


class TestEarlyStopping:
    def test_stops_after_patience(self) -> None:
        stopper = EarlyStopping(monitor="val_loss", patience=1, mode="min")
        # improve, then two non-improving epochs -> stop on the second.
        state = _run_epochs(stopper, [1.0, 1.0, 1.0], metric="val_loss")
        assert state.stop_training is True
        assert state.history == []  # helper does not append history

    def test_does_not_stop_when_improving(self) -> None:
        stopper = EarlyStopping(monitor="val_loss", patience=0, mode="min")
        state = _run_epochs(stopper, [1.0, 0.9, 0.8], metric="val_loss")
        assert state.stop_training is False
        assert stopper.best == pytest.approx(0.8)

    def test_max_mode(self) -> None:
        stopper = EarlyStopping(monitor="acc", patience=0, mode="max")
        state = _run_epochs(stopper, [0.5, 0.4], metric="acc")
        assert state.stop_training is True

    def test_missing_metric_is_ignored(self) -> None:
        stopper = EarlyStopping(monitor="val_loss", patience=0)
        state = TrainerState(epochs=1)
        stopper.on_epoch_end(state, {"loss": 1.0})
        assert state.stop_training is False

    def test_invalid_mode(self) -> None:
        with pytest.raises(ValueError, match="mode"):
            EarlyStopping(mode="sideways")

    def test_negative_patience(self) -> None:
        with pytest.raises(ValueError, match="patience"):
            EarlyStopping(patience=-1)


class TestModelCheckpoint:
    def test_records_best_epoch(self) -> None:
        checkpoint = ModelCheckpoint(monitor="val_loss", mode="min")
        state = _run_epochs(checkpoint, [1.0, 0.5, 0.7], metric="val_loss")
        assert checkpoint.best == pytest.approx(0.5)
        assert checkpoint.best_epoch == 1
        assert state.best_epoch == 1
        assert state.best_metric == pytest.approx(0.5)

    def test_missing_metric_ignored(self) -> None:
        checkpoint = ModelCheckpoint(monitor="val_loss")
        state = TrainerState()
        checkpoint.on_epoch_end(state, {"loss": 1.0})
        assert checkpoint.best_epoch == -1

    def test_save_best_only_false_updates_every_epoch(self) -> None:
        checkpoint = ModelCheckpoint(
            monitor="val_loss", mode="min", save_best_only=False
        )
        _run_epochs(checkpoint, [1.0, 2.0], metric="val_loss")
        assert checkpoint.best_epoch == 1  # last epoch recorded even if worse

    def test_invalid_mode(self) -> None:
        with pytest.raises(ValueError, match="mode"):
            ModelCheckpoint(mode="nope")


class TestLoggingCallback:
    def test_logs_without_error(self) -> None:
        logger_cb = LoggingCallback(every_n_epochs=1)
        state = TrainerState(epochs=2)
        logger_cb.on_train_begin(state)
        state.epoch = 0
        logger_cb.on_epoch_end(state, {"loss": 0.5})
        state.epoch = 1
        logger_cb.on_epoch_end(state, {"loss": 0.4})
        logger_cb.on_train_end(state)

    def test_every_n_epochs_cadence(self) -> None:
        logger_cb = LoggingCallback(every_n_epochs=5)
        state = TrainerState(epochs=10)
        # epoch 0 is neither a multiple of 5 nor the last -> skipped path.
        state.epoch = 0
        logger_cb.on_epoch_end(state, {"loss": 1.0})

    def test_train_end_without_best_epoch(self) -> None:
        logger_cb = LoggingCallback()
        state = TrainerState(epochs=1)
        state.history.append({"loss": 1.0})
        logger_cb.on_train_end(state)  # best_epoch == -1 branch

    def test_invalid_cadence(self) -> None:
        with pytest.raises(ValueError, match="every_n_epochs"):
            LoggingCallback(every_n_epochs=0)
