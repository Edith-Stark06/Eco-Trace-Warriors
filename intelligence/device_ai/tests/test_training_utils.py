"""Tests for the training utility helpers (milestone M1.3)."""

from __future__ import annotations

import time

import pytest

from device_ai.training.utils import (
    describe_environment,
    git_commit_hash,
    resolve_device,
    seed_everything,
)
from device_ai.training.utils.git_utils import UNKNOWN_COMMIT, git_is_dirty
from device_ai.training.utils.timing import Timer


def test_git_commit_hash_returns_string() -> None:
    commit = git_commit_hash()
    assert isinstance(commit, str)
    assert commit  # non-empty (a real hash or the "unknown" sentinel)


def test_git_commit_hash_unknown_on_bad_cwd(tmp_path) -> None:
    # A path with no git repo above it should not exist as a repo; the helper
    # must degrade to the sentinel rather than raise.
    commit = git_commit_hash(cwd=tmp_path / "definitely" / "missing")
    assert commit == UNKNOWN_COMMIT


def test_git_is_dirty_returns_bool() -> None:
    assert isinstance(git_is_dirty(), bool)


def test_seed_everything_returns_seed_and_is_deterministic() -> None:
    import random

    assert seed_everything(123) == 123
    first = [random.random() for _ in range(3)]
    seed_everything(123)
    second = [random.random() for _ in range(3)]
    assert first == second


def test_seed_everything_rejects_negative() -> None:
    with pytest.raises(ValueError, match="seed"):
        seed_everything(-1)


def test_resolve_device_variants() -> None:
    assert resolve_device("cpu") == "cpu"
    assert resolve_device("auto") in {"cpu", "cuda"}
    # An explicit request is honoured verbatim after normalisation.
    assert resolve_device("cuda") in {"cpu", "cuda"}


def test_describe_environment_keys() -> None:
    env = describe_environment()
    assert {
        "device",
        "gpu",
        "python",
        "platform",
        "processor",
        "torch",
        "executable",
    } <= set(env)


class TestTimer:
    def test_context_manager_measures_elapsed(self) -> None:
        with Timer("x") as timer:
            time.sleep(0.001)
        assert timer.elapsed >= 0.0
        # elapsed_ms is elapsed*1000 rounded to 3 decimals.
        assert timer.elapsed_ms == pytest.approx(timer.elapsed * 1000, abs=1e-3)

    def test_start_stop_returns_duration(self) -> None:
        timer = Timer("y")
        timer.start()
        duration = timer.stop()
        assert duration >= 0.0

    def test_elapsed_while_running(self) -> None:
        timer = Timer("running")
        timer.start()
        # Reading elapsed before stop() takes the live-interval branch.
        assert timer.elapsed >= 0.0
        timer.stop()

    def test_stop_before_start_raises(self) -> None:
        with pytest.raises(RuntimeError):
            Timer("z").stop()
