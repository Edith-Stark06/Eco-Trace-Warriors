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

## Real-training infrastructure failure and fix (2026-09-06, notebook versions 3-4)

**Version 3** (`DRY_RUN=False`, first real-training attempt) errored after
~51s with **0 epochs completed** and no weights produced:
```
RuntimeError: Dataset '.../ecotrace-p442-yolo11n-gpu-v1/data.yaml' error ❌
Dataset '.../data.yaml' images not found, missing path '/kaggle/working/images/val'
```
Root cause: the attached dataset's `data.yaml` has `path: .` (relative).
Ultralytics' `check_det_dataset()` resolves that `.` against the **process's
current working directory** (`/kaggle/working`, where the notebook runs),
not against `data.yaml`'s own directory — so it looked for
`/kaggle/working/images/val` instead of the real
`/kaggle/input/datasets/edithstark/ecotrace-p442-yolo11n-gpu-v1/images/val`.
The Phase 3/4 dry-runs never caught this because the script's own validation
(section 3-4) reads images/labels directly off the discovered absolute
`dataset_root`, never exercising Ultralytics' own yaml-driven resolution —
that only happens inside `model.train()`/`model.val()` itself.

**Fix (section 4b in the script)**: write a separate runtime copy of the
yaml under `/kaggle/working/ecotrace_p442_runtime_data.yaml` (never touching
the source Kaggle dataset) with `path` rewritten to the discovered absolute
`dataset_root`, and `train`/`val`/`test`/`nc`/`names` preserved unchanged.
`TRAIN_KWARGS["data"]` and the later `model.val()` calls all point at this
runtime yaml instead of the source one.

**Proof, not assumption**: section 4b calls
`ultralytics.data.utils.check_det_dataset()` directly against the runtime
yaml — the same resolver `model.train()` uses internally — and hard-fails
unless every resolved train/val/test path exists on disk and its image
count matches the expected `763/164/92`.

**Version 4** (recovery dry-run, `DRY_RUN=True`, same fixed script) ran
clean end-to-end: resolved runtime yaml `path` =
`/kaggle/input/datasets/edithstark/ecotrace-p442-yolo11n-gpu-v1`, resolved
`train`/`val`/`test` counts `763/164/92` (exact match), `nc==8` + exact
class names confirmed via the resolver's own output, GPU hard gate passed
(`2x Tesla T4`).

## Real training result (2026-09-06, kernel version 5, candidate — NOT production)

Under explicit authorization, a local copy with `DRY_RUN=False` (plus a
repeat of the section 4b/5 gates immediately before `model.train()`, added
for this run) was pushed as version 5. All 50 epochs completed normally —
`patience=20` never triggered early stopping. Wall-clock training duration:
~1003s (~16.7 min); total kernel run ~1051s (~17.5 min).

- **Candidate checkpoint**: `best.pt` SHA256
  `4a441d0a64519eadf5a72a79422e723929c11b2b5065d9bdc3567745d86412fb`
  (5,444,954 bytes) — best epoch 46 of 50 by validation mAP50-95.
  **Different from, and never derived from, the production checkpoint.**
- **Test-split metrics** (92 images): precision 0.580, recall 0.538,
  mAP50 0.612, mAP50-95 0.447.
- **Weakest classes**: smartphone (AP50 0.316, precision 0.163, recall 0.20)
  and laptop (AP50 0.347) — both far below the others. Strongest: printer
  (AP50 0.870), monitor (AP50 0.809, precision 0.864).
- Production checkpoint SHA256 re-verified unchanged after this run:
  `c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92`.
- Candidate artifacts (best.pt/last.pt, results.csv, args.yaml, plots,
  confusion matrices, run_summary.json) remain under
  `/kaggle/working/ecotrace_p442_gpu_v1/` on Kaggle only — never promoted,
  copied, or committed into this repository.

This is one experimental candidate result, not a production decision.
Promotion (if ever warranted) is a separate, explicit, human-approved step.

## Same-test production baseline found (Phase 4.1)

A genuine same-test-set production evaluation already existed —
`E:\Ecotrace Dataset\training\p4_4_2_bulk_balance_v1\metrics.json`, written
by the original training pipeline itself against this exact 763/164/92
split (confirmed: checkpoint SHA256 in that file's `best_checkpoint`
matches production exactly). **Production beats the GPU candidate overall**
(test mAP50 0.664 vs 0.612; mAP50-95 0.510 vs 0.447), almost entirely
because of one class: **smartphone AP50 0.625 (production) vs 0.316 (GPU
candidate)** on the identical data — laptop and mouse are statistically
unchanged between the two. Confusion-matrix comparison shows a
smartphone↔tablet confusion present in the GPU candidate but **absent**
in production, pointing at a GPU-training-run-specific regression rather
than a data problem for smartphone specifically (laptop's weakness, by
contrast, is consistent across both models — likely a genuine data/
class-boundary issue, not training-specific).

## GPU reproducibility investigation (2026-09-06, kernel version 6)

Re-ran the *exact* version 5 recipe unchanged (same script, same
`TRAIN_KWARGS`, same seed=42/deterministic=True, same `amp` left at
Ultralytics' CUDA default of `True`) to check whether the smartphone
collapse was run-to-run noise. **Result: bit-for-bit identical metrics**
— test precision/recall/mAP50/mAP50-95 and every per-class AP50/AP50-95/
precision/recall matched version 5 to the full floating-point precision
printed (e.g. smartphone AP50 `0.3155686630369026` both runs, mAP50-95
`0.44654538779903624` both runs). `best.pt`/`last.pt` SHA256 differ from
version 5's (checkpoint files typically embed a training timestamp/run
metadata even when the underlying weights are identical), but the
identical metrics to 16 significant figures make it very unlikely the
weights themselves differ.

**Conclusion: REPRODUCIBLE GPU REGRESSION, not random run variance.** The
smartphone collapse is a deterministic property of this exact recipe +
GPU + AMP configuration, confirmed by an independent, byte-for-byte-clean
second run under the same infra gates (T4x2, functional CUDA test,
dataset resolver, 763/164/92, taxonomy — all re-verified and passed
identically). This strengthens the case that Ultralytics' `amp=True`
default (live on CUDA, a no-op on the original CPU production run, never
declared as an intentional GPU-vs-CPU change alongside `device`/`workers`)
is the most plausible unproven variable. An `amp=False` isolation
config (`AMP_FALSE_TRAIN_KWARGS` in the script) has been prepared but
**not run** — pending separate explicit authorization.

## AMP isolation experiment (2026-09-06, kernel version 7)

Ran the single authorized `amp=False` experiment: `AMP_ISOLATION_MODE`
flipped to `True` locally, selecting `AMP_FALSE_TRAIN_KWARGS` (identical
to `TRAIN_KWARGS` except `amp=False`) for `model.train()`. Confirmed at
the Ultralytics engine level, not just this script's own print — the
`engine/trainer:` args dump shows `amp=False` with every other argument
byte-identical to v5/v6's dump. **Environment note**: Ultralytics
auto-installed `8.4.142` this run (v5/v6 used `8.4.141` — a patch-level
bump on Kaggle's pip index between runs, not something this project
controlled or intended; recorded here rather than silently assumed
identical).

**Result — materially better, but not equivalent to production**: all 50
epochs completed (best epoch 50, still improving at the end). Test mAP50
0.636 (vs 0.612 AMP=True, vs 0.664 production) and mAP50-95 0.490 (vs
0.447 AMP=True, vs 0.510 production) — recovers roughly half-to-most of
the AMP=True-vs-production gap. Per-class AP50 improved for all three
previously-weak classes: smartphone 0.316→**0.426** (+0.110), laptop
0.347→**0.433** (+0.087, now above production's own 0.363), mouse
0.410→**0.441** (+0.031). Precision dropped slightly (0.580→0.557) while
recall rose more (0.538→0.586).

**Verdict: MIXED / INCONCLUSIVE — AMP contributes to performance
differences, but does not fully explain the regression.** Smartphone
specifically only recovered about a third of its total shortfall against
production (0.426 vs the production run's 0.625 on the same test set) —
a real, substantial improvement, but the "key regression" the isolation
was designed to explain is not fully closed. AMP is a real contributing
factor to the GPU-vs-CPU gap, not the sole cause; something else in the
GPU/software stack (or genuine seed/AMP-interaction sensitivity specific
to smartphone) still accounts for the remaining difference. No further
training was run after this one experiment, per instruction.
