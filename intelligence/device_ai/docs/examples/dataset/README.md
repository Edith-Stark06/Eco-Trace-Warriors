# Example dataset pipeline artifacts (P4.1.2)

These files are **illustrative** outputs of the P4.1.2 dataset engineering
pipeline, checked in for reference. They are regenerated at runtime under the
managed `datasets/` tree (which is gitignored) and are **not** read by the
service.

| File | Produced by | Written at runtime to |
|---|---|---|
| `metadata.json` | `build_metadata_document` (per-image metadata + quality) | `datasets/metadata/metadata.json` |
| `statistics.json` | `StatisticsCalculator.compute` → `statistics_to_dict` | `datasets/quality/report.json` (statistics section) |
| `validation_report.json` | `ImageValidator.validate` → `image_validation_to_dict` | quality report tooling |

## Regenerating

The artifacts are **byte-stable** — the generator injects a fixed clock
(`2026-01-15T14:30:00+00:00`) and builds every image from fixed arithmetic
patterns (no randomness). To regenerate them, from `intelligence/` with
`PYTHONPATH=.`:

```bash
python -m device_ai.scripts.gen_dataset_examples
```

## What the example shows

The example is a tiny **five-image synthetic dataset** — four device images
(`laptop_field_000001.png`, `smartphone_lab_000042.png`,
`tablet_donor_000003.png`, `monitor_ewaste_000017.png`) plus one exact byte-copy
(`laptop_field_000001_copy.png`). Each device image is a sinusoidal grating at a
distinct orientation and frequency, so the four carry **pairwise-distinct
perceptual hashes** and are never mistaken for near-duplicates. It demonstrates:

- **Per-image metadata** (`metadata.json`) — format, mode, resolution,
  megapixels, size, the four content/perceptual hashes (SHA-256, aHash, dHash,
  pHash), and quality metrics (blur score, brightness) with derived flags.
- **Quality flagging** — `monitor_ewaste_000017.png` is a low-detail grating and
  is flagged **blurry** (low variance-of-Laplacian); `tablet_donor_000003.png`
  is flagged **bright** (mean luminance above the threshold).
- **Exact-duplicate detection** (`statistics.json`) — the byte-copy folds in as
  **one** duplicate group / one duplicate image, with **no spurious
  near-duplicates**.
- **Structural validation** (`validation_report.json`) — the byte-copy is
  surfaced as a single `DUPLICATE_HASH` issue, so `is_valid` is `false`.

Hash digests are deterministic functions of the (synthetic) image bytes; on a
real dataset they carry the same meaning but different values.
