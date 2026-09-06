"""EcoTrace India — P4.4.2 GPU reproduction (Kaggle kernel).

Reproduces the exact P4.4.2 YOLO11n training recipe on a Kaggle GPU
runtime, as a NEW, SEPARATE candidate checkpoint. The production
checkpoint (dataset_acquisition/training/p4_4_2_bulk_balance_v1/runs/
p442_yolo11n/weights/best.pt, SHA256
c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92) is
never read, downloaded, or written by this script.

Confirmed baseline recipe (from the production run's own args.yaml,
E:\\Ecotrace Dataset\\training\\p4_4_2_bulk_balance_v1\\runs\\p442_yolo11n\\
args.yaml — unchanged here):
    model=yolo11n.pt (Ultralytics pretrained), epochs=50, patience=20,
    batch=8, imgsz=512, seed=42, deterministic=True, cache=False,
    project/name -> runs/p442_yolo11n, plots=True, verbose=True.
    Everything else (lr0, augmentation, optimizer="auto"->AdamW, etc.)
    is left at Ultralytics' own defaults, exactly as the production run
    did — none of it is touched here.

The ONLY intentional infrastructure changes for GPU, both isolated to
one place below (TRAIN_KWARGS) and nowhere else:
    device: "cpu" -> 0            (first CUDA GPU)
    workers: 0 -> 2                (Kaggle GPU notebooks have more CPU
                                     headroom than the constrained local
                                     host the production run used; 2 is
                                     a conservative, documented choice —
                                     not "however many cores exist")

Controlled by DRY_RUN below. With DRY_RUN=True (the default — Phase 3),
sections 1-7 and 9 (partially) execute; the actual model.train() call
in section 8 is never reached. Section 8's code is present so the same
file is what Phase 4 runs unchanged, only flipping DRY_RUN to False.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resting state is always True. Flipped locally to False for kernel version
# 5 (2026-09-06, first real run) and version 6 (reproducibility run, same
# recipe, unchanged) — see README.md's "GPU reproducibility investigation"
# section. Never commit this as False.
# ---------------------------------------------------------------------------
DRY_RUN = True

# ---------------------------------------------------------------------------
# Resting state is always False (regular recipe, amp left at Ultralytics'
# CUDA default of True). Flipped locally to True for the single Phase 4.3
# AMP-isolation run (kernel version 7, 2026-09-06) — selected
# AMP_FALSE_TRAIN_KWARGS below instead of TRAIN_KWARGS, changing exactly
# one variable (amp) and nothing else; confirmed at the Ultralytics engine
# level too (engine/trainer args dump showed amp=False, everything else
# identical to v5/v6). See README's "AMP isolation experiment" section for
# the result. Never commit this as True.
# ---------------------------------------------------------------------------
AMP_ISOLATION_MODE = False

# ---------------------------------------------------------------------------
# Resting state is always None (install whatever ultralytics pip resolves,
# as every prior run did). Set to an exact version string ONLY for a
# controlled version-isolation experiment (Phase 4.4, kernel version 8,
# "8.4.141") — Phase 4.3/v7 auto-installed 8.4.142 (a PyPI patch bump
# between pushes, not intended), confounding the AMP=False comparison
# against v5/v6's 8.4.141. When set, section 1 hard-fails (never silently
# substitutes a different version) if the pin cannot be installed exactly.
# Never commit this as non-None.
# ---------------------------------------------------------------------------
PINNED_ULTRALYTICS_VERSION = None

# ---------------------------------------------------------------------------
# Resting state is always False (original 763-image train set, dataset slug
# ecotrace-p442-yolo11n-gpu-v1). Flipped locally to True ONLY for the single
# Phase 5.2 expanded-training-set experiment (kernel version 9) — selects
# the private edithstark/ecotrace-p442-expanded-train-v1 dataset (Phase
# 5.1's audited 1099/164/92 construction: 763 original + 336 COCO-derived
# smartphone/laptop/mouse images; val/test are the original, byte-identical,
# frozen splits) instead of the original 763-train dataset. Everything else
# (recipe, AMP, Ultralytics version) stays exactly as Phase 4.4/v8. Never
# commit this as True.
# ---------------------------------------------------------------------------
EXPANDED_DATASET_MODE = False

# Phase 2 artifacts, recorded here for the training-arguments audit trail
# (section 8's saved metadata), not read/verified against anything at runtime.
KAGGLE_DATASET_ID = (
    "edithstark/ecotrace-p442-expanded-train-v1" if EXPANDED_DATASET_MODE
    else "edithstark/ecotrace-p442-yolo11n-gpu-v1"
)
KAGGLE_DATASET_VERSION = 1
PHASE2_MANIFEST_SHA256 = "f64580240ab29ce7c939c208cdf88c6b16afcd36de5686c3895918e8793a67ff"

EXPECTED_CLASS_NAMES = {
    0: "laptop",
    1: "smartphone",
    2: "tablet",
    3: "monitor",
    4: "printer",
    5: "mouse",
    6: "camera",
    7: "headphones",
}
EXPECTED_COUNTS = (
    {"train": 1099, "val": 164, "test": 92} if EXPANDED_DATASET_MODE
    else {"train": 763, "val": 164, "test": 92}
)

OUTPUT_DIR = Path("/kaggle/working/ecotrace_p442_gpu_v1")


def _fail(message: str) -> None:
    """Print a clearly-marked failure and stop the kernel (non-zero exit)."""
    print(f"\n[STOP] {message}")
    sys.exit(1)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 1. Environment
# ---------------------------------------------------------------------------
print("=" * 70)
print("1. ENVIRONMENT")
print("=" * 70)
print("Python:", sys.version.split()[0])

try:
    import torch
except ImportError:
    _fail("PyTorch is not importable in this Kaggle environment.")

try:
    import ultralytics as _preexisting_ultralytics
    _preexisting_ultralytics_version = _preexisting_ultralytics.__version__
except ImportError:
    _preexisting_ultralytics_version = None

if PINNED_ULTRALYTICS_VERSION is not None:
    if _preexisting_ultralytics_version != PINNED_ULTRALYTICS_VERSION:
        print(
            f"Installing PINNED ultralytics=={PINNED_ULTRALYTICS_VERSION} "
            f"(found: {_preexisting_ultralytics_version}) for a controlled "
            "version-isolation experiment (enable_internet required)..."
        )
        import subprocess

        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q",
             f"ultralytics=={PINNED_ULTRALYTICS_VERSION}"],
            check=True,
        )
    # Force a clean re-import bound to whatever is on disk now, rather than
    # trust a partially-initialized module object from the try block above.
    for _mod_name in list(sys.modules):
        if _mod_name == "ultralytics" or _mod_name.startswith("ultralytics."):
            del sys.modules[_mod_name]
    import ultralytics
    from ultralytics import YOLO
    if ultralytics.__version__ != PINNED_ULTRALYTICS_VERSION:
        _fail(
            f"ultralytics version pin FAILED: requested "
            f"{PINNED_ULTRALYTICS_VERSION}, got {ultralytics.__version__}. "
            "Refusing to proceed with an unpinned/wrong version for this "
            "controlled experiment — never silently substitute a version."
        )
    print(f"ultralytics version pin CONFIRMED: {ultralytics.__version__}")
elif _preexisting_ultralytics_version is None:
    # Kaggle's base Python image does not ship ultralytics by default
    # (unlike torch/numpy/pandas) — install it now. enable_internet=true
    # in kernel-metadata.json is required for this to succeed.
    print("ultralytics not present — installing via pip (enable_internet required)...")
    import subprocess

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "ultralytics"],
        check=True,
    )
    import ultralytics
    from ultralytics import YOLO
else:
    import ultralytics
    from ultralytics import YOLO

print("PyTorch:", torch.__version__)
print("Ultralytics:", ultralytics.__version__)
print("CUDA available (torch.cuda.is_available()):", torch.cuda.is_available())
cuda_functional = False
if torch.cuda.is_available():
    print("CUDA version:", torch.version.cuda)
    print("GPU name:", torch.cuda.get_device_name(0))
    props = torch.cuda.get_device_properties(0)
    print("GPU VRAM (GB):", round(props.total_memory / (1024**3), 2))
    print("GPU compute capability: sm_%d%d" % (props.major, props.minor))

    # torch.cuda.is_available() only checks that a CUDA device is visible —
    # it does NOT confirm this PyTorch build's compiled kernels actually
    # support that device's compute capability. A P100 (sm_60) reporting
    # is_available()=True while lacking sm_60 kernel binaries is a real,
    # observed Kaggle failure mode: the device is "available" but unusable.
    # Do an actual GPU matmul to confirm real, functional CUDA support.
    try:
        _a = torch.randn(64, 64, device="cuda")
        _b = torch.randn(64, 64, device="cuda")
        _ = (_a @ _b).sum().item()
        cuda_functional = True
        print("Functional CUDA smoke test (matmul on GPU): PASSED")
    except RuntimeError as exc:
        print(f"Functional CUDA smoke test (matmul on GPU): FAILED — {exc}")


# ---------------------------------------------------------------------------
# 2. Dataset discovery
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("2. DATASET DISCOVERY")
print("=" * 70)
print(f"EXPANDED_DATASET_MODE={EXPANDED_DATASET_MODE} -> dataset={KAGGLE_DATASET_ID}, "
      f"expected counts={EXPECTED_COUNTS}")

# Kaggle mounts a dataset with slug `ecotrace-p442-yolo11n-gpu-v1` (or, in
# EXPANDED_DATASET_MODE, `ecotrace-p442-expanded-train-v1`) at a fixed,
# predictable path — discovered here, never hardcoded as a Windows path
# (this dataset carries no dataset_working-style stale absolute path; its
# data.yaml was rewritten in Phase 2 to `path: .`, relative).
DATASET_SLUG = KAGGLE_DATASET_ID.split("/")[-1]
kaggle_input = Path("/kaggle/input")

# Kaggle's actual mount nesting under /kaggle/input varies (observed here:
# input/datasets/<owner>/<slug>/, not the shorter input/<slug>/ some Kaggle
# docs describe) — search for the slug directory rather than assuming one
# fixed layout, and require it to actually contain data.yaml.
dataset_root = None
if kaggle_input.is_dir():
    for candidate in kaggle_input.rglob(DATASET_SLUG):
        if candidate.is_dir() and (candidate / "data.yaml").exists():
            dataset_root = candidate
            break

if dataset_root is None:
    all_data_yamls = (
        sorted(str(p.relative_to(kaggle_input)) for p in kaggle_input.rglob("data.yaml"))
        if kaggle_input.is_dir() else []
    )
    _fail(
        f"Kaggle dataset '{DATASET_SLUG}' not found (no directory named "
        f"'{DATASET_SLUG}' containing data.yaml under /kaggle/input). "
        f"data.yaml files actually found under /kaggle/input: {all_data_yamls}. "
        "Is it attached to this kernel (dataset_sources in kernel-metadata.json)?"
    )
print("Resolved dataset root:", dataset_root)

data_yaml_path = dataset_root / "data.yaml"
if not data_yaml_path.exists():
    _fail(f"data.yaml not found at {data_yaml_path}")
print("data.yaml path:", data_yaml_path)

required_dirs = [
    "images/train", "images/val", "images/test",
    "labels/train", "labels/val", "labels/test",
]
missing_dirs = [d for d in required_dirs if not (dataset_root / d).is_dir()]
if missing_dirs:
    _fail(f"Missing expected directories under dataset root: {missing_dirs}")
print("All required image/label directories present:", required_dirs)


# ---------------------------------------------------------------------------
# 3 & 4. Dataset integrity + class/taxonomy validation
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("3-4. DATASET INTEGRITY + TAXONOMY VALIDATION")
print("=" * 70)

try:
    import yaml
except ImportError:
    _fail("PyYAML is not importable — cannot parse data.yaml.")

with data_yaml_path.open("r", encoding="utf-8") as fh:
    data_cfg = yaml.safe_load(fh)

print("Parsed data.yaml:", json.dumps(data_cfg, indent=2))

nc = data_cfg.get("nc")
if nc != 8:
    _fail(f"data.yaml nc={nc}, expected exactly 8. Refusing to proceed.")

names = data_cfg.get("names") or {}
names = {int(k): v for k, v in names.items()}
if names != EXPECTED_CLASS_NAMES:
    _fail(
        f"data.yaml class names {names} do not exactly match the expected "
        f"frozen 8-class set {EXPECTED_CLASS_NAMES}. Refusing to proceed — "
        "this must never silently invent or reorder classes."
    )
print("nc == 8 and class names match exactly:", EXPECTED_CLASS_NAMES)

counts = {}
label_errors = []
for split in ("train", "val", "test"):
    img_dir = dataset_root / "images" / split
    lbl_dir = dataset_root / "labels" / split
    images = sorted(p.stem for p in img_dir.glob("*.jpg"))
    labels = sorted(p.stem for p in lbl_dir.glob("*.txt"))
    counts[split] = len(images)

    missing_labels = sorted(set(images) - set(labels))
    orphan_labels = sorted(set(labels) - set(images))
    if missing_labels:
        label_errors.append(f"{split}: {len(missing_labels)} image(s) with no label file")
    if orphan_labels:
        label_errors.append(f"{split}: {len(orphan_labels)} label file(s) with no image")

    # Validate every label file: class id in [0,7], 5 whitespace-separated
    # numeric fields, normalized coordinates in [0,1].
    for stem in labels:
        lbl_path = lbl_dir / f"{stem}.txt"
        with lbl_path.open("r", encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh if ln.strip()]
        for line in lines:
            parts = line.split()
            if len(parts) != 5:
                label_errors.append(f"{lbl_path}: malformed line '{line}'")
                continue
            try:
                cid = int(parts[0])
                coords = [float(x) for x in parts[1:]]
            except ValueError:
                label_errors.append(f"{lbl_path}: non-numeric line '{line}'")
                continue
            if not (0 <= cid <= 7):
                label_errors.append(f"{lbl_path}: class id {cid} outside 0-7")
            if not all(0.0 <= c <= 1.0 for c in coords):
                label_errors.append(f"{lbl_path}: coordinate out of [0,1] in '{line}'")

    print(f"{split}: images={len(images)} labels={len(labels)}")

if label_errors:
    print(f"\n{len(label_errors)} label integrity issue(s) found:")
    for err in label_errors[:20]:
        print(" -", err)
    _fail("Label integrity check failed — refusing to train on corrupted data.")

if counts != EXPECTED_COUNTS:
    _fail(
        f"Split counts {counts} do not match the expected Phase 2 counts "
        f"{EXPECTED_COUNTS}. The Kaggle dataset may be incomplete or "
        "different from what was uploaded — refusing to proceed."
    )
print("Split counts match Phase 2 exactly:", EXPECTED_COUNTS)
print("Zero missing image/label pairs, zero orphan labels, zero invalid class ids.")


# ---------------------------------------------------------------------------
# 4b. Runtime dataset YAML + real Ultralytics dataset-resolution proof
#
# ROOT CAUSE of kernel version 3's infrastructure failure (0 epochs, no
# weights): the attached dataset's own data.yaml has `path: .`. Ultralytics'
# check_det_dataset() resolves that relative `path` against the CURRENT
# WORKING DIRECTORY the training process runs from (/kaggle/working), not
# against data.yaml's own directory — so it looked for
# /kaggle/working/images/val instead of the real
# /kaggle/input/datasets/<owner>/<slug>/images/val. The Phase 3 dry-run never
# caught this because its own validation above reads images/labels directly
# off `dataset_root` (an absolute path), never exercising Ultralytics' own
# yaml-driven path resolution.
#
# Fix: write a SEPARATE runtime copy of the yaml, under /kaggle/working/
# (never touching the source Kaggle dataset), with `path` rewritten to the
# discovered absolute dataset_root and train/val/test/nc/names preserved
# exactly as authored. Then PROVE — with Ultralytics' own resolver, not just
# our own os.path checks — that this runtime yaml resolves correctly before
# ever reaching model.train().
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("4b. RUNTIME DATASET YAML + ULTRALYTICS RESOLUTION PROOF")
print("=" * 70)

runtime_data_cfg = dict(data_cfg)
runtime_data_cfg["path"] = str(dataset_root.resolve())
# train/val/test/nc/names are carried over unchanged from the source yaml —
# only `path` is rewritten to an absolute value.

runtime_yaml_path = Path("/kaggle/working/ecotrace_p442_runtime_data.yaml")
runtime_yaml_path.parent.mkdir(parents=True, exist_ok=True)
with runtime_yaml_path.open("w", encoding="utf-8") as fh:
    yaml.safe_dump(runtime_data_cfg, fh, sort_keys=False)

print(f"Runtime YAML written to: {runtime_yaml_path}")
print("Runtime YAML contents:")
print(runtime_yaml_path.read_text(encoding="utf-8"))

# Real Ultralytics dataset resolution test — the exact function
# model.train() itself calls internally (ultralytics.data.utils.
# check_det_dataset), invoked here standalone against the runtime yaml,
# so a resolution failure is caught now rather than mid-model.train().
from ultralytics.data.utils import check_det_dataset

resolved = check_det_dataset(str(runtime_yaml_path))

resolved_split_paths = {}
resolved_split_counts = {}
for split in ("train", "val", "test"):
    entry = resolved.get(split)
    paths = entry if isinstance(entry, list) else [entry]
    paths = [Path(p) for p in paths if p is not None]
    resolved_split_paths[split] = [str(p) for p in paths]

    missing = [p for p in paths if not p.is_dir()]
    if missing:
        _fail(
            f"Ultralytics dataset-resolution proof FAILED for split '{split}': "
            f"resolved path(s) {[str(p) for p in paths]} do not exist as "
            f"directories (missing: {[str(p) for p in missing]}). The runtime "
            "YAML fix did not work — refusing to proceed to training."
        )
    image_count = sum(len(list(p.glob("*.jpg"))) for p in paths)
    resolved_split_counts[split] = image_count
    print(f"Resolved '{split}' path(s): {[str(p) for p in paths]} -> {image_count} images")

if resolved_split_counts != EXPECTED_COUNTS:
    _fail(
        f"Ultralytics-resolved image counts {resolved_split_counts} do not "
        f"match the expected {EXPECTED_COUNTS}. Refusing to proceed."
    )
print(f"\nUltralytics dataset-resolution proof PASSED: resolved counts "
      f"{resolved_split_counts} match {EXPECTED_COUNTS} exactly, using the "
      "SAME resolver model.train() uses internally — not just this "
      "script's own os.path checks.")

resolved_nc = resolved.get("nc")
resolved_names = resolved.get("names") or {}
resolved_names = {int(k): v for k, v in resolved_names.items()}
if resolved_nc != 8 or resolved_names != EXPECTED_CLASS_NAMES:
    _fail(
        f"Ultralytics-resolved nc={resolved_nc}/names={resolved_names} do "
        f"not match the expected 8-class taxonomy {EXPECTED_CLASS_NAMES}."
    )
print("Ultralytics-resolved nc==8 and class names match exactly:", EXPECTED_CLASS_NAMES)


# ---------------------------------------------------------------------------
# 5. GPU validation (hard stop if unavailable — never silently fall back to CPU)
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("5. GPU VALIDATION")
print("=" * 70)
if not torch.cuda.is_available():
    _fail(
        "CUDA is not available in this Kaggle environment. This script "
        "must not silently fall back to CPU — check that the kernel was "
        "pushed with enable_gpu=true and an accelerator is attached."
    )
if not cuda_functional:
    _fail(
        "torch.cuda.is_available() is True, but the functional GPU matmul "
        "smoke test in section 1 FAILED — this PyTorch build's compiled "
        "kernels do not support the assigned GPU's compute capability "
        "(observed on Kaggle's default Tesla P100 allocation, sm_60, "
        "against a PyTorch build supporting only sm_70+). Training would "
        "silently produce garbage or crash mid-run. Do not proceed — "
        "request a different accelerator (e.g. T4 x2) or a PyTorch build "
        "with sm_60 support."
    )

# Explicit named hard gate, in addition to the functional smoke test above:
# only proceed on a known-good T4 allocation. Phase 3 found the account's
# GPU pool can silently hand back an incompatible P100 (sm_60) even when
# the notebook is configured for GPU — check the actual device name/count
# directly rather than trusting the requested accelerator type.
gpu_count = torch.cuda.device_count()
gpu_names = [torch.cuda.get_device_name(i) for i in range(gpu_count)]
print(f"GPU count: {gpu_count}")
print(f"GPU names: {gpu_names}")
if not all("T4" in name for name in gpu_names):
    _fail(
        f"GPU hard gate failed: expected T4-class GPU(s), got {gpu_names}. "
        "Refusing to proceed — this notebook must only train on T4/T4x2, "
        "never P100 or any other unverified accelerator."
    )
print("GPU hard gate passed: all detected GPU(s) are T4-class.")
print("CUDA is available and functionally confirmed — GPU validation passed.")


# ---------------------------------------------------------------------------
# 6. Model initialization
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("6. MODEL INITIALIZATION")
print("=" * 70)
BASE_MODEL = "yolo11n.pt"
print(f"Loading Ultralytics pretrained base model: {BASE_MODEL}")
print("(This is the stock Ultralytics-hosted pretrained checkpoint — NOT")
print(" the protected production artifact, which this script never touches.)")
model = YOLO(BASE_MODEL)
print("Model architecture:", model.model.__class__.__name__)
print("Model task:", model.task)


# ---------------------------------------------------------------------------
# 7. Training configuration
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("7. TRAINING CONFIGURATION")
print("=" * 70)

# Byte-for-byte the P4.4.2 recipe except the two GPU-infrastructure fields
# called out at the top of this file (device, workers) — see the module
# docstring. Nothing else here differs from the production run's args.yaml.
# `data` points at the runtime YAML (section 4b), not the source dataset's
# own data.yaml — same train/val/test/nc/names, only `path` made absolute.
TRAIN_KWARGS = dict(
    data=str(runtime_yaml_path),
    epochs=50,
    imgsz=512,
    batch=8,
    patience=20,
    device=0,          # GPU change 1/2: was "cpu" in production
    workers=2,          # GPU change 2/2: was 0 in production (see docstring)
    cache=False,
    seed=42,
    deterministic=True,
    project=str(OUTPUT_DIR / "runs"),
    name="p442_yolo11n_gpu",
    exist_ok=True,
    plots=True,
    verbose=True,
)
print(json.dumps(TRAIN_KWARGS, indent=2))

# ---------------------------------------------------------------------------
# Ultralytics defaults amp=True on CUDA (a no-op on the original CPU
# production run, but live here) — this was never declared as an
# intentional GPU change alongside device/workers, and kernel version 5's
# smartphone AP50 collapse (0.625 production -> 0.316 candidate, same test
# set, laptop/mouse unaffected), independently reproduced bit-for-bit by
# version 6, makes AMP the leading unproven variable (see README's "GPU
# reproducibility investigation" section). AMP_ISOLATION_MODE selects this
# instead of TRAIN_KWARGS for section 8 — the ONLY difference from
# TRAIN_KWARGS is amp=False; everything else is the identical dict.
# ---------------------------------------------------------------------------
AMP_FALSE_TRAIN_KWARGS = dict(TRAIN_KWARGS, amp=False)
ACTIVE_TRAIN_KWARGS = AMP_FALSE_TRAIN_KWARGS if AMP_ISOLATION_MODE else TRAIN_KWARGS
print(f"\nAMP_ISOLATION_MODE={AMP_ISOLATION_MODE} -> "
      f"amp={ACTIVE_TRAIN_KWARGS.get('amp', 'Ultralytics default (True on CUDA)')}")

run_record = {
    "phase": "3-dry-run" if DRY_RUN else ("4.3-amp-isolation" if AMP_ISOLATION_MODE else "4-real-training"),
    "base_model": BASE_MODEL,
    "train_kwargs": ACTIVE_TRAIN_KWARGS,
    "python_version": platform.python_version(),
    "torch_version": torch.__version__,
    "ultralytics_version": ultralytics.__version__,
    "cuda_version": torch.version.cuda,
    "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    "kaggle_dataset_id": KAGGLE_DATASET_ID,
    "kaggle_dataset_version": KAGGLE_DATASET_VERSION,
    "phase2_manifest_sha256": PHASE2_MANIFEST_SHA256,
    "production_checkpoint_sha256_not_used_as_input": (
        "c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92"
    ),
}
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
run_record_path = OUTPUT_DIR / "run_arguments.json"
with run_record_path.open("w", encoding="utf-8") as fh:
    json.dump(run_record, fh, indent=2)
print(f"\nRun arguments recorded to {run_record_path}")


# ---------------------------------------------------------------------------
# 8. Training — NEVER reached while DRY_RUN is True.
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("8. TRAINING")
print("=" * 70)
if DRY_RUN:
    print("DRY_RUN=True — skipping model.train(). No GPU training performed.")
    print("Sections 9-14 (validation/evaluation/comparison/export) require a")
    print("real training run and are not executed in this phase.")
else:
    # Immediate pre-train rechecks: sections 4b/5's gates already ran above,
    # but the recipe explicitly requires re-verifying right before
    # model.train() rather than trusting checks that happened a few
    # sections earlier.
    if not torch.cuda.is_available():
        _fail("Pre-train recheck failed: CUDA no longer available.")
    _recheck_count = torch.cuda.device_count()
    _recheck_names = [torch.cuda.get_device_name(i) for i in range(_recheck_count)]
    if not all("T4" in name for name in _recheck_names):
        _fail(
            f"Pre-train GPU recheck failed: expected T4-class GPU(s), got "
            f"{_recheck_names}. Refusing to start training."
        )
    try:
        _ra = torch.randn(64, 64, device="cuda")
        _rb = torch.randn(64, 64, device="cuda")
        _ = (_ra @ _rb).sum().item()
    except RuntimeError as exc:
        _fail(f"Pre-train functional CUDA smoke test FAILED: {exc}")
    print(f"Pre-train GPU recheck passed: count={_recheck_count}, names={_recheck_names}, "
          "functional CUDA smoke test PASSED")

    # Re-verify the runtime dataset YAML resolves identically, right before
    # training — the exact same proof as section 4b, repeated here so a
    # training start is never gated on a check performed sections earlier.
    _pretrain_resolved = check_det_dataset(str(runtime_yaml_path))
    _pretrain_counts = {}
    for split in ("train", "val", "test"):
        entry = _pretrain_resolved.get(split)
        paths = entry if isinstance(entry, list) else [entry]
        paths = [Path(p) for p in paths if p is not None]
        if any(not p.is_dir() for p in paths):
            _fail(f"Pre-train dataset recheck failed for split '{split}': {paths}")
        _pretrain_counts[split] = sum(len(list(p.glob("*.jpg"))) for p in paths)
    if _pretrain_counts != EXPECTED_COUNTS:
        _fail(f"Pre-train dataset recheck: counts {_pretrain_counts} != {EXPECTED_COUNTS}")
    _pretrain_nc = _pretrain_resolved.get("nc")
    _pretrain_names = {int(k): v for k, v in (_pretrain_resolved.get("names") or {}).items()}
    if _pretrain_nc != 8 or _pretrain_names != EXPECTED_CLASS_NAMES:
        _fail(f"Pre-train dataset recheck: taxonomy mismatch nc={_pretrain_nc} names={_pretrain_names}")
    print(f"Pre-train dataset recheck passed: counts={_pretrain_counts}, "
          f"nc=8, taxonomy matches {EXPECTED_CLASS_NAMES}")

    import time as _time

    train_start = _time.time()
    results = model.train(**ACTIVE_TRAIN_KWARGS)  # noqa: F841 - Phase 4 only
    train_duration_seconds = _time.time() - train_start
    print(f"\nTraining wall-clock duration: {train_duration_seconds:.1f}s "
          f"({train_duration_seconds / 60:.1f} min)")

    # -----------------------------------------------------------------
    # 9. Validation / 10. Test evaluation / 11. Per-class metrics
    # -----------------------------------------------------------------
    best_path = OUTPUT_DIR / "runs" / "p442_yolo11n_gpu" / "weights" / "best.pt"
    last_path = OUTPUT_DIR / "runs" / "p442_yolo11n_gpu" / "weights" / "last.pt"
    val_results = model.val(data=str(runtime_yaml_path), split="val")
    test_results = model.val(data=str(runtime_yaml_path), split="test")

    per_class = {}
    box = test_results.box
    result_names = test_results.names if hasattr(test_results, "names") else {}
    for i, ci in enumerate(box.ap_class_index):
        per_class[result_names.get(int(ci), str(int(ci)))] = {
            "ap50": float(box.ap50[i]),
            "ap50_95": float(box.ap[i]),
            "precision": float(box.p[i]),
            "recall": float(box.r[i]),
        }
    print("Per-class test metrics:", json.dumps(per_class, indent=2))

    # -----------------------------------------------------------------
    # 12. Artifact hashing/sizing/latency — the candidate is hashed and
    # recorded, never compared for equality with the production checkpoint
    # and never copied over docker_data/device_ai/models/best.pt.
    # -----------------------------------------------------------------
    candidate_sha256 = None
    last_sha256 = None
    best_size_bytes = None
    last_size_bytes = None
    if best_path.exists():
        candidate_sha256 = sha256_file(best_path)
        best_size_bytes = best_path.stat().st_size
        print(f"Candidate best.pt SHA256: {candidate_sha256}")
        print(f"Candidate best.pt path: {best_path}")
        print(f"Candidate best.pt size: {best_size_bytes} bytes")
        print(
            "This SHA256 is DIFFERENT from the production checkpoint's "
            "c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92 "
            "by construction — it is a new training run, and the production "
            "file was never read as input."
        )
    if last_path.exists():
        last_sha256 = sha256_file(last_path)
        last_size_bytes = last_path.stat().st_size
        print(f"Candidate last.pt SHA256: {last_sha256}")
        print(f"Candidate last.pt size: {last_size_bytes} bytes")

    # Inference latency: average single-image forward-pass time on the
    # trained candidate, over the test split's images (warmup + timed runs).
    inference_latency_ms = None
    if best_path.exists():
        latency_model = YOLO(str(best_path))
        test_images = sorted((dataset_root / "images" / "test").glob("*.jpg"))[:20]
        if test_images:
            for warmup_img in test_images[:3]:
                latency_model.predict(str(warmup_img), device=0, verbose=False)
            _lat_start = _time.time()
            for img in test_images:
                latency_model.predict(str(img), device=0, verbose=False)
            inference_latency_ms = (
                (_time.time() - _lat_start) / len(test_images) * 1000
            )
            print(
                f"Mean inference latency over {len(test_images)} test images: "
                f"{inference_latency_ms:.1f} ms/image"
            )

    # -----------------------------------------------------------------
    # 13. Baseline comparison — structure only; the actual baseline
    # metrics must be supplied out-of-band (Phase 4/5 local evaluation
    # against the same held-out test split), not fabricated here.
    # -----------------------------------------------------------------
    comparison = {
        "baseline": {
            "name": "P4.4.2 production",
            "sha256": "c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92",
            "metrics": "TO BE FILLED IN from the existing production evaluation record",
        },
        "candidate": {
            "name": "P4.4.2 GPU reproduction",
            "sha256": candidate_sha256 if best_path.exists() else None,
            "metrics": {
                "precision": float(box.mp) if hasattr(box, "mp") else None,
                "recall": float(box.mr) if hasattr(box, "mr") else None,
                "map50": float(box.map50) if hasattr(box, "map50") else None,
                "map50_95": float(box.map) if hasattr(box, "map") else None,
                "per_class": per_class,
            },
        },
    }
    comparison_path = OUTPUT_DIR / "baseline_comparison.json"
    with comparison_path.open("w", encoding="utf-8") as fh:
        json.dump(comparison, fh, indent=2)
    print(f"Comparison scaffold written to {comparison_path}")

    # -----------------------------------------------------------------
    # Full run summary — everything the final structured report needs,
    # in one file, alongside the run's own results.csv/args.yaml/plots.
    # -----------------------------------------------------------------
    val_box = val_results.box
    run_summary = {
        "train_duration_seconds": train_duration_seconds,
        # `results` (model.train()'s return value) carries final validation
        # metrics, not an epoch counter; the trainer itself tracks the last
        # completed epoch (0-indexed) as model.trainer.epoch.
        "epochs_completed": (
            int(model.trainer.epoch) + 1 if getattr(model, "trainer", None) is not None else None
        ),
        "best_pt": {
            "path": str(best_path),
            "sha256": candidate_sha256,
            "size_bytes": best_size_bytes,
        },
        "last_pt": {
            "path": str(last_path),
            "sha256": last_sha256,
            "size_bytes": last_size_bytes,
        },
        "inference_latency_ms_per_image": inference_latency_ms,
        "val_metrics": {
            "precision": float(val_box.mp) if hasattr(val_box, "mp") else None,
            "recall": float(val_box.mr) if hasattr(val_box, "mr") else None,
            "map50": float(val_box.map50) if hasattr(val_box, "map50") else None,
            "map50_95": float(val_box.map) if hasattr(val_box, "map") else None,
        },
        "test_metrics": comparison["candidate"]["metrics"],
    }
    run_summary_path = OUTPUT_DIR / "run_summary.json"
    with run_summary_path.open("w", encoding="utf-8") as fh:
        json.dump(run_summary, fh, indent=2)
    print(f"Run summary written to {run_summary_path}")

    # -----------------------------------------------------------------
    # 14. Candidate export — the candidate stays under OUTPUT_DIR only.
    # No copy is made to docker_data/device_ai/models/best.pt or anywhere
    # resembling the production path. Promotion is a separate, explicit,
    # human-approved step outside this script.
    # -----------------------------------------------------------------
    print(f"\nCandidate artifacts remain under {OUTPUT_DIR} — not exported ")
    print("or promoted anywhere. Promotion requires explicit separate approval.")

print("\n" + "=" * 70)
print("DONE" if DRY_RUN else "TRAINING RUN COMPLETE")
print("=" * 70)
