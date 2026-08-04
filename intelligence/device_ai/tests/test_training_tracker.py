"""Tests for the experiment trackers (milestone M1.3)."""

from __future__ import annotations

import json
from pathlib import Path

from device_ai.configs.settings import Settings
from device_ai.training.experiments import (
    JsonExperimentTracker,
    NullTracker,
    build_tracker,
    mlflow_available,
)
from device_ai.training.experiments.mlflow import build_mlflow_tracker


class TestJsonExperimentTracker:
    def test_writes_params_metrics_meta(self, tmp_path: Path) -> None:
        tracker = JsonExperimentTracker(tmp_path)
        assert tracker.backend == "json"
        with tracker.run(
            run_id="run-1", experiment_name="exp", config={"lr": 0.1}
        ) as run:
            assert run.run_id == "run-1"
            run.log_params({"epochs": 3})
            run.log_metrics({"loss": 1.0}, step=0)
            run.log_metrics({"loss": 0.5}, step=1)
            run.set_summary({"training_time": 2.5})

        run_dir = tmp_path / "run-1"
        params = json.loads((run_dir / "params.json").read_text())
        metrics = json.loads((run_dir / "metrics.json").read_text())
        meta = json.loads((run_dir / "meta.json").read_text())
        assert params == {"lr": 0.1, "epochs": 3}
        assert [entry["loss"] for entry in metrics] == [1.0, 0.5]
        assert metrics[0]["step"] == 0
        assert meta["run_id"] == "run-1"
        assert meta["experiment_name"] == "exp"
        assert meta["summary"]["training_time"] == 2.5

    def test_from_settings(self, training_settings: Settings) -> None:
        tracker = JsonExperimentTracker.from_settings(training_settings)
        assert tracker.root == training_settings.mlruns_dir

    def test_run_without_config(self, tmp_path: Path) -> None:
        tracker = JsonExperimentTracker(tmp_path)
        with tracker.run(run_id="r") as run:
            run.log_metrics({"a": 1.0}, step=0)
        assert (tmp_path / "r" / "params.json").read_text() == "{}"


class TestNullTracker:
    def test_records_nothing(self, tmp_path: Path) -> None:
        tracker = NullTracker()
        assert tracker.backend == "none"
        with tracker.run(run_id="x", config={"a": 1}) as run:
            assert run.run_id == "x"
            run.log_params({"a": 1})
            run.log_metrics({"loss": 1.0}, step=0)
            run.set_summary({"done": True})
        # No files created anywhere.
        assert list(tmp_path.iterdir()) == []


class TestBuildTracker:
    def test_json_default(self, training_settings: Settings) -> None:
        assert build_tracker(training_settings).backend == "json"

    def test_none(self, tmp_path: Path) -> None:
        settings = Settings(experiment_tracker="none", mlruns_dir=tmp_path)
        assert build_tracker(settings).backend == "none"

    def test_mlflow_falls_back_to_json_when_absent(self, tmp_path: Path) -> None:
        settings = Settings(experiment_tracker="mlflow", mlruns_dir=tmp_path)
        # MLflow is not installed in the base env, so we fall back to JSON.
        tracker = build_tracker(settings)
        assert tracker.backend == "json"


def test_mlflow_helpers_report_absence(training_settings: Settings) -> None:
    assert mlflow_available() is False
    assert build_mlflow_tracker(training_settings) is None
