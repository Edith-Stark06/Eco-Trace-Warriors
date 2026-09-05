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

## GPU history

**Script-kernel dry runs (2026-09-05, `ecotrace-p4-4-2-gpu-dry-run-v1`,
versions 1-5)**: this account's GPU accelerator pool assigned a **Tesla P100
(compute capability sm_60)**, incompatible with Kaggle's pre-installed
PyTorch build (`2.10.0+cu128`, supports `sm_70`+ only). `torch.cuda.is_available()`
returned `True` (device *visible*) but any real CUDA op failed:
`CUDA error: no kernel image is available for execution on the device`.
Confirmed deterministic across two separate pushes (versions 3 and 5), not
transient. The functional smoke test (an actual GPU matmul, not just
`is_available()`) caught this and hard-stopped rather than training on CPU
or crashing mid-run.

**Resolved (2026-09-06, notebook `notebook0bbb1ac713`, version 2)**: a real
Kaggle *notebook* (not a script kernel) was created via the web UI with
`machine_shape: NvidiaTeslaT4` explicitly set, and the private dataset
attached. Pushing this same `train_p442_gpu.py` logic (embedded as the
notebook's one code cell — same file, unchanged recipe, not a second
divergent script) to that notebook produced a clean run: **2x Tesla T4**,
`sm_75`, functional smoke test passed. A second, explicit named hard gate
was added (`gpu_names`/`"T4" in name` check, not just the functional test)
per instruction, so a future P100 reallocation fails loudly and immediately
even if some future PyTorch build happens to support `sm_60`.

Do not attempt to route around either check by disabling it — training on
an unverified accelerator would silently corrupt or crash.

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
