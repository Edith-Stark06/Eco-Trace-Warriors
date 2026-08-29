import json
import shutil
from pathlib import Path

repo = Path.cwd()

signoff_path = (
    repo
    / "dataset_acquisition/review/p4_3_4_multiclass_qa_v1/signoff_template.json"
)

label_roots = {
    "smartphone": repo / "dataset_acquisition/staging/openimages_smartphone_v1/labels",
    "tablet": repo / "dataset_acquisition/staging/openimages_multiclass_v1/openimages_tablet_v1/labels",
    "monitor": repo / "dataset_acquisition/staging/openimages_multiclass_v1/openimages_monitor_v1/labels",
    "printer": repo / "dataset_acquisition/staging/openimages_multiclass_v1/openimages_printer_v1/labels",
}

candidate = repo / "dataset_acquisition/candidate/p4_3_5_dataset_v1_candidate"
images_root = candidate / "images"
labels_root = candidate / "labels"

data = json.loads(signoff_path.read_text(encoding="utf-8"))
accepted = [x for x in data["signoff"] if x["status"] == "QA_ACCEPTED"]

if len(accepted) != 257:
    raise SystemExit(
        f"REFUSING: expected 257 QA_ACCEPTED items, found {len(accepted)}"
    )

if not images_root.is_dir():
    raise SystemExit(f"REFUSING: candidate images directory missing: {images_root}")

# Verify candidate image set before creating labels.
for item in accepted:
    cls = item["class"]
    filename = item["canonical_image_filename"]

    image = images_root / cls / filename

    if not image.is_file():
        raise SystemExit(
            f"REFUSING: accepted image missing from candidate: {cls}/{filename}"
        )

# Refuse if labels already exist; avoids silently overwriting candidate data.
if labels_root.exists():
    raise SystemExit(
        f"REFUSING: candidate labels directory already exists: {labels_root}"
    )

labels_root.mkdir(parents=True)

copied = 0
missing = []

for item in accepted:
    cls = item["class"]
    image_filename = item["canonical_image_filename"]
    label_filename = Path(image_filename).with_suffix(".txt").name

    src = label_roots[cls] / label_filename
    dst_dir = labels_root / cls
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / label_filename

    if not src.is_file():
        missing.append(f"{cls}/{label_filename}")
        continue

    shutil.copy2(src, dst)
    copied += 1

if missing:
    shutil.rmtree(labels_root)
    raise SystemExit(
        f"REFUSING: {len(missing)} accepted labels are missing. "
        f"Examples: {missing[:10]}"
    )

print(f"Labels copied: {copied}")
print("Expected labels: 257")
print("Source staging was not modified.")
