# Example dataset artifacts (M1.2)

These files are **illustrative** outputs of the dataset intelligence pipeline,
checked in for reference. They are regenerated at runtime under the managed
`datasets/` tree (which is gitignored) and are **not** read by the service.

| File | Produced by | Written at runtime to |
|---|---|---|
| `metadata.json` | `DatasetService.generate_metadata` | `datasets/metadata/metadata.json` |
| `report.json` | `DatasetService.build_report` | `datasets/quality/report.json` |
| `report.html` | `DatasetService.build_report` | `datasets/quality/report.html` |

The example corresponds to a tiny three-image dataset (`a.png`, a near-black
`b.png`, and `dup.png` — an exact byte-copy of `a.png`) with a single YOLO
label for `a.png`. It demonstrates:

- **exact duplicate** detection (`a.png` ↔ `dup.png`, distance 0),
- **quality flagging** (`b.png` is dark and blurry),
- **annotation validation** surfacing images without labels.

Hash digests in `metadata.json` are representative placeholders; the real
values are deterministic functions of the image bytes.
