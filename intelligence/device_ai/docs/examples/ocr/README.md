# Example OCR artifacts (M1.6)

These files are **illustrative** outputs of the OCR Intelligence Engine,
checked in for reference. They are generated from the deterministic
`MockOCRBackend` and `MockBarcodeReader` — **no real EasyOCR/OpenCV model is
downloaded or executed** (the base environment has neither `easyocr` nor
`opencv-python-headless`). The spans/barcodes are the mocks', standing in for a
real OCR backend; the response *shapes* are exactly what the live endpoints
return.

| File | Produced by | Live endpoint equivalent |
|---|---|---|
| `extract_response.json` | `OCRService.extract` → `OCRExtraction.to_dict` | `POST /ocr/extract` |
| `parse_examples.json` | `OCRParser.parse` over labelled noisy-input cases | `POST /ocr/parse` |
| `evaluation_report.json` | Per-field accuracy over the labelled synthetic set | (evaluation, not an endpoint) |
| `evaluation_report.md` | Markdown rendering of `evaluation_report.json` | (evaluation, not an endpoint) |

## Regenerating

The artifacts are **byte-stable** — the generator injects a fixed clock
(`2026-08-01T12:00:00Z`) and the mocks' deterministic, hash-derived spans and
barcodes. To regenerate them, from `intelligence/` with `PYTHONPATH=.`:

```bash
python -m device_ai.scripts.gen_ocr_examples
```

## What the examples show

- **`extract_response.json`** — the full `/ocr/extract` result over one
  synthetic device image: the winning `fields` (manufacturer/model/serial/IMEI/
  MAC/QR/barcode, each confidence-scored), the raw `spans` and decoded
  `barcodes`, the small `identity` projection the fingerprint engine can
  consume, the `engine_name`/`engine_version`, `created_at`, and the
  `source_hashes` (image provenance). Note the mock derives a **Luhn-valid**
  IMEI and a colon-normalized MAC from the image content hash, so the same image
  always extracts the same identity.
- **`parse_examples.json`** — four **noisy-input → parsed-field** cases exercising
  the normalization layer directly (no image): a clean label block, an IMEI +
  MAC pair (hyphen → colon normalization), a QR whose payload is **mined** for a
  serial, and a 1-D barcode whose payload is mined for an **IMEI**. Each case
  records the exact `input` spans/barcodes and the full parser `output`.
- **`evaluation_report.{json,md}`** — a **field-level evaluation** of the parser
  over a small **labelled synthetic set** (the same four cases). It reports
  per-field accuracy, an overall accuracy, and a mean field confidence — the raw
  material a per-field confidence threshold is chosen from. The mock inputs are
  clean by construction, so accuracy is `1.0`; the value of the report is the
  **confidence distribution** (e.g. a Luhn-valid IMEI scores ≈ 0.93–0.98, a
  barcode-mined serial ≈ 0.70), which is what a real, noisier EasyOCR read would
  be scored against.

The full engine, backend interface, pattern/validator table, parser design,
barcode/QR decoding, configuration, DI/guarded-swap and the optional
fingerprint-identity seam are documented in
[`docs/engineering/ocr.md`](../../engineering/ocr.md).
