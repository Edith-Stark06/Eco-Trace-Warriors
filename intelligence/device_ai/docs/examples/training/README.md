# Example training-platform artifacts (M1.3)

These files are **illustrative** outputs of the AI training & MLOps platform,
checked in for reference. They are produced by the reusable training lifecycle
running against the in-repo **mock** trainer — **no real model is trained,
downloaded or exported** (per the M1.3 scope). At runtime the equivalent files
are written under the gitignored `artifacts/` and `mlruns/` trees and are
**not** read by the service.

| File | Produced by | Written at runtime to |
|---|---|---|
| `model_registry.json` | `ModelRegistry.register` (auto-called by `BaseTrainer.fit`) | `artifacts/model_registry.json` |
| `training_history.json` | the `TrainingHistory` returned by `BaseTrainer.fit` | (returned in-process; not persisted) |
| `evaluation.json` | `Evaluator.evaluate` (also written by `python -m device_ai.evaluate`) | `artifacts/reports/<model>-<version>.json` |
| `evaluation.html` | `Evaluator.to_html` | `artifacts/reports/<model>-<version>.html` |

## Regenerating

The artifacts are byte-stable — the generator injects a fixed clock
(`2026-07-31T12:00:00`) and commit (`23a1b3a`), and the mock metrics are
deterministic. To regenerate them, from `intelligence/` with `PYTHONPATH=.`:

```bash
python -m device_ai.scripts.gen_training_examples
```

## What the example shows

- **Provenance capture** — `model_registry.json` records the model name,
  version, dataset version, timestamp, git commit, framework, metrics, export
  formats and artifact location for a single mock run.
- **Lifecycle output** — `training_history.json` is the value object returned by
  `fit()`: per-epoch metrics, the selected best epoch and the resolved device.
- **Evaluation reporting** — `evaluation.json` / `evaluation.html` are a
  three-class classification report (accuracy, macro precision/recall/F1, a
  confusion matrix) with the inference-benchmark section shown as a clearly
  labelled **placeholder** (no model executes in M1.3).

The `artifact_location` in `model_registry.json` is rewritten to a stable
relative path for portability; a real run records the absolute checkpoint path.
