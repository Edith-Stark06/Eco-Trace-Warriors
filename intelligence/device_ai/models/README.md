# Model Artifacts

This directory holds **versioned model artifacts** for the Device
Intelligence Engine. Binaries are **not** committed to Git
(`docs/engineering/08_AI.md` → Model Management); they are fetched at build
or startup from release artifacts / object storage.

## Layout convention

```
models/
├── detector/
│   └── detector-<semver>/
│       ├── model.onnx        # or model.pt
│       └── metadata.json     # training date, dataset version, metrics
├── clip/
│   └── clip-<semver>/
├── condition/
│   └── condition-<semver>/
└── ocr/
    └── ocr-<semver>/
```

The `ModelRegistry` (`device_ai/inference/registry.py`) resolves an
artifact directory as:

```
<MODEL_DIR>/<component>/<component>-<version>/
```

`MODEL_DIR` comes from configuration (`settings.model_dir`) — paths are
never hardcoded in adapter code.

## Milestone M1.1

No artifacts exist yet. The service runs with deterministic **mock**
implementations. When a real model is integrated, drop its versioned folder
here (or mount it as a volume) and point the corresponding adapter at the
registry-resolved path.
