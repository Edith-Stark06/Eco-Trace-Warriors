# Example detector evaluation artifacts (M1.4)

These files are **illustrative** outputs of the Device Detection Engine's
evaluation harness, checked in for reference. They are rendered from a small
**fake** ``model.val()`` result — **no real model is trained, downloaded or
executed** (the base environment has neither Ultralytics nor torch). The numbers
are representative placeholders standing in for a real Ultralytics validation on
a fine-tuned YOLO detector.

At runtime the equivalent files are written under the gitignored
`artifacts/reports/` tree by `DetectionEvaluator.build_document` /
`DetectionEvaluator.to_html`.

| File | Produced by | Written at runtime to |
|---|---|---|
| `evaluation.json` | `DetectionEvaluator.build_document` | `artifacts/reports/<model>-<version>.json` |
| `evaluation.html` | `DetectionEvaluator.to_html` | `artifacts/reports/<model>-<version>.html` |

## Regenerating

The artifacts are byte-stable — the generator injects a fixed clock
(`2026-07-31T12:00:00`) and the fake metrics are deterministic. To regenerate
them, from `intelligence/` with `PYTHONPATH=.`:

```bash
python -m device_ai.scripts.gen_detector_examples
```

## What the example shows

- **Detection metrics** — `precision`, `recall`, `mAP50`, `mAP50_95` extracted
  from the Ultralytics `results_dict`, plus a **derived `f1`**
  (`2·P·R / (P+R)`). These four (device type / confidence / bounding box are the
  real prediction outputs; the rest of the `/predict` response stays a
  placeholder in M1.4).
- **Confusion matrix** — a four-class matrix (`laptop`, `smartphone`, `tablet`,
  `monitor`) with the extra Ultralytics **`background`** row/column appended, so
  the axes line up in the rendered report.
- **Inference benchmark** — a clearly-labelled **placeholder** section (shared
  with the M1.3 evaluation report): real latency/throughput numbers are deferred
  to a later benchmarking pass.

The report shares the training platform's evaluation surface
(`build_evaluation_document` + `Evaluator`) — only the detection-specific
metric/confusion *extraction* is new (see `training/detector/evaluation.py`).
