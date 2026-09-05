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
# Flip to False only in Phase 4, after Phase 3's dry run has passed cleanly.
# ---------------------------------------------------------------------------
DRY_RUN = True

# Phase 2 artifacts, recorded here for the training-arguments audit trail
# (section 8's saved metadata), not read/verified against anything at runtime.
KAGGLE_DATASET_ID = "edithstark/ecotrace-p442-yolo11n-gpu-v1"
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
EXPECTED_COUNTS = {"train": 763, "val": 164, "test": 92}

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
    import ultralytics
    from ultralytics import YOLO
except ImportError:
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

# Kaggle mounts a dataset with slug `ecotrace-p442-yolo11n-gpu-v1` at a
# fixed, predictable path — discovered here, never hardcoded as a Windows
# path (this dataset carries no dataset_working-style stale absolute path;
# its data.yaml was rewritten in Phase 2 to `path: .`, relative).
DATASET_SLUG = "ecotrace-p442-yolo11n-gpu-v1"
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
TRAIN_KWARGS = dict(
    data=str(data_yaml_path),
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

run_record = {
    "phase": "3-dry-run" if DRY_RUN else "4-real-training",
    "base_model": BASE_MODEL,
    "train_kwargs": TRAIN_KWARGS,
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
    results = model.train(**TRAIN_KWARGS)  # noqa: F841 - Phase 4 only

    # -----------------------------------------------------------------
    # 9. Validation / 10. Test evaluation / 11. Per-class metrics
    # -----------------------------------------------------------------
    best_path = OUTPUT_DIR / "runs" / "p442_yolo11n_gpu" / "weights" / "best.pt"
    val_results = model.val(data=str(data_yaml_path), split="val")
    test_results = model.val(data=str(data_yaml_path), split="test")

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
    # 12. Artifact hashing — the candidate is hashed and recorded, never
    # compared for equality with the production checkpoint and never
    # copied over docker_data/device_ai/models/best.pt.
    # -----------------------------------------------------------------
    if best_path.exists():
        candidate_sha256 = sha256_file(best_path)
        print(f"Candidate best.pt SHA256: {candidate_sha256}")
        print(f"Candidate best.pt path: {best_path}")
        print(
            "This SHA256 is DIFFERENT from the production checkpoint's "
            "c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92 "
            "by construction — it is a new training run, and the production "
            "file was never read as input."
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
