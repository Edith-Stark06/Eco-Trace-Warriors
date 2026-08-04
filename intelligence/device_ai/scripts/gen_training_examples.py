"""Generate illustrative training-platform artifacts for docs/examples/training.

Runs the mock training lifecycle end to end with an injected fixed clock and
commit (so the output is byte-stable), then renders an evaluation report. The
resulting model-registry entry and evaluation JSON/HTML are copied into
``docs/examples/training/`` for reference. Nothing here trains a real model.

Usage (from ``intelligence/`` with ``PYTHONPATH=.``)::

    python -m device_ai.scripts.gen_training_examples
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from device_ai.configs.settings import Settings
from device_ai.training.config import RunConfig
from device_ai.training.core.evaluator import Evaluator
from device_ai.training.core.trainer import BaseTrainer

_FIXED_CLOCK = datetime(2026, 7, 31, 12, 0, 0)
_FIXED_COMMIT = "23a1b3a"
_EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "docs" / "examples" / "training"


class _ExampleTrainer(BaseTrainer):
    """A tiny deterministic trainer used only to produce example artifacts."""

    framework = "mock"
    monitor_metric = "val_loss"
    monitor_mode = "min"

    def build_model(self) -> dict[str, float]:
        return {"weight": 0.0}

    def train_loader(self) -> list[int]:
        return [0, 1, 2, 3]

    def val_loader(self) -> list[int]:
        return [0, 1]

    def train_step(self, model: Any, batch: Any) -> dict[str, float]:
        return {"loss": round(1.0 / (batch + 1), 4)}

    def validation_step(self, model: Any, batch: Any) -> dict[str, float]:
        return {"loss": round(0.5 / (batch + 1), 4)}


def _build_config() -> RunConfig:
    return RunConfig.model_validate(
        {
            "model_name": "device-detector",
            "trainer": "mock",
            "experiment_name": "die-training",
            "training": {
                "epochs": 3,
                "batch_size": 4,
                "device": "cpu",
                "seed": 7,
                "model_version": "1.0.0",
            },
            "tags": {"milestone": "M1.3", "stage": "platform"},
        }
    )


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    """Generate the example artifacts into ``docs/examples/training``."""
    _EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        settings = Settings(
            artifact_dir=root / "artifacts",
            mlruns_dir=root / "mlruns",
            experiment_tracker="json",
        )
        trainer = _ExampleTrainer(
            _build_config(),
            settings,
            clock=lambda: _FIXED_CLOCK,
            commit=_FIXED_COMMIT,
        )
        history = trainer.fit()

        # 1) The auto-registered model-registry catalogue. The artifact
        # location is rewritten from the throwaway temp path to a stable,
        # illustrative relative path so the checked-in example is portable.
        registry_records = json.loads(
            trainer.artifacts.registry_file.read_text(encoding="utf-8")
        )
        for entry in registry_records:
            entry["artifact_location"] = (
                f"artifacts/checkpoints/{entry['name']}-{entry['version']}.pt"
            )
        (_EXAMPLES_DIR / "model_registry.json").write_text(
            json.dumps(registry_records, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        # 2) A training-history summary (the fit() return value).
        _write(
            _EXAMPLES_DIR / "training_history.json",
            {
                "model_name": history.model_name,
                "model_version": history.model_version,
                "run_id": history.run_id,
                "epochs_completed": history.epochs_completed,
                "best_epoch": history.best_epoch,
                "best_metric": history.best_metric,
                "final_metrics": history.final_metrics,
                "git_commit": history.git_commit,
                "device": history.device,
                "epochs": [
                    {"epoch": epoch.epoch, "metrics": epoch.metrics}
                    for epoch in history.epochs
                ],
            },
        )

        # 3) An evaluation report (JSON + self-contained HTML).
        evaluator = Evaluator()
        document = evaluator.evaluate(
            model_name="device-detector",
            model_version="1.0.0",
            y_true=[0, 1, 2, 0, 1, 2, 0, 1],
            y_pred=[0, 1, 2, 0, 2, 2, 0, 1],
            class_names=["battery", "phone", "laptop"],
            generated_at=_FIXED_CLOCK,
            dataset_version="v1",
        )
        _write(_EXAMPLES_DIR / "evaluation.json", document)
        (_EXAMPLES_DIR / "evaluation.html").write_text(
            evaluator.to_html(document), encoding="utf-8"
        )

    print(f"Wrote example artifacts to {_EXAMPLES_DIR}")


if __name__ == "__main__":
    main()
