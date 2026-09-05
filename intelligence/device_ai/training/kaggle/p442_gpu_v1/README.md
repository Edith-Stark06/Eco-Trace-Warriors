# P4.4.2 GPU reproduction — Kaggle kernel

Reproduces the P4.4.2 YOLO11n production recipe on a Kaggle GPU runtime as a
**new, separate candidate checkpoint**. Never reads, downloads, or writes the
production checkpoint (`docker_data/device_ai/models/best.pt`, SHA256
`c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92`).

## Files

- `train_p442_gpu.py` — the kernel script. A `DRY_RUN` flag at the top gates
  the actual `model.train()` call; everything before it (environment checks,
  dataset discovery, integrity/taxonomy validation, GPU validation, model
  init, argument recording) always runs.
- `kernel-metadata.json` — Kaggle kernel metadata (GPU enabled, internet
  enabled for the `ultralytics` pip install, attaches the private dataset
  `edithstark/ecotrace-p442-yolo11n-gpu-v1`).

## Recipe

Byte-for-byte the production P4.4.2 run (`epochs=50, patience=20, batch=8,
imgsz=512, seed=42, deterministic=True, cache=False`), confirmed from that
run's own `args.yaml`. The only intentional changes, both isolated to
`TRAIN_KWARGS` in the script: `device` (`"cpu"` → `0`) and `workers` (`0` →
`2`, a conservative documented value — Kaggle GPU notebooks have more CPU
headroom than the constrained local host the production run used).

## Running it

```
python -m kaggle kernels push -p intelligence/device_ai/training/kaggle/p442_gpu_v1 -t 300
python -m kaggle kernels status edithstark/ecotrace-p4-4-2-gpu-dry-run-v1
PYTHONUTF8=1 python -m kaggle kernels output edithstark/ecotrace-p4-4-2-gpu-dry-run-v1 -p <local-dir> -o
```

(`PYTHONUTF8=1` works around a `charmap` codec crash in the Kaggle CLI's own
log-writing code on Windows — otherwise `output` fails with a `UnicodeEncodeError`
before writing anything.)

## Known blocker (2026-09-05, kernel versions 1-5)

**Real training cannot proceed yet.** This account's Kaggle GPU accelerator
pool currently assigns a **Tesla P100 (compute capability sm_60)**, but the
pre-installed PyTorch build on Kaggle's Python image is `2.10.0+cu128`, which
only supports `sm_70` and above. `torch.cuda.is_available()` returns `True`
(the device is *visible*), but any real CUDA op fails:

```
CUDA error: no kernel image is available for execution on the device
```

This is deterministic, not transient — confirmed identically on two separate
pushes (versions 3 and 5). The script's section-1 functional smoke test
(an actual GPU matmul, not just `is_available()`) catches this and hard-stops
in section 5 rather than silently training on CPU or crashing mid-run.

Before Phase 4 (real training), one of these needs to happen:
- Request a different accelerator for the kernel (e.g. a T4 x2, which this
  PyTorch build does support) — the CLI/metadata schema used here
  (`enable_gpu: "true"`) does not expose a specific-accelerator-type field;
  this may require the Kaggle web UI's notebook editor accelerator picker,
  or a `--accelerator` CLI value discovered/tested separately.
- Or install a PyTorch build with `sm_60` support in the kernel before
  importing `ultralytics`.

Do not attempt to route around this by disabling the functional check —
training would silently corrupt or crash.

## Dataset path discovery

Kaggle's actual `/kaggle/input` mount nesting was `.../datasets/<owner>/<slug>/`,
not the `/kaggle/input/<slug>/` shape some Kaggle docs describe. The script
searches for the dataset by slug name via `rglob` rather than assuming a
fixed layout — verified working (kernel version 5's log correctly resolved
`/kaggle/input/datasets/edithstark/ecotrace-p442-yolo11n-gpu-v1`).

## Verified dry-run result (kernel version 5)

Dataset discovery, directory presence, `nc==8` + exact class names, and
train/val/test counts (`763/164/92`, zero missing/orphan labels, zero
invalid class ids) all passed — matching Phase 2's manifest exactly. GPU
quota consumed across all 5 dry-run attempts: 0.03h of 30h weekly.
