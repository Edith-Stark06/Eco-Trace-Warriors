# P4.3.1 Multi-Class Acquisition Report (Open Images V7 → EcoTrace)

Status: Complete (one bounded real pilot performed)
Sprint: P4.3.1 — Production multi-class dataset acquisition orchestration
Run label: `p4_3_1`
Injected timestamp: `2026-08-09T00:00:00+00:00` (the wall clock is never read)
Conversion version: `openimages-multiclass-v1`

> **This report records only what actually happened on disk.** Every count below
> is derived from real files and the frozen tools' own reports — nothing is
> fabricated. **Dataset v1.0 is not released.** No class was auto-approved; the
> pilot class ends at **`QA_PENDING`**, awaiting human review.

---

## 1. What was run

A single bounded, real acquisition was performed for exactly **one** remaining
MAPPED class to exercise the full path end to end
(download → convert → validate → `QA_PENDING`):

```bash
python scripts/acquire_openimages_multiclass.py --class smartphone --limit 20
```

- **Pilot class:** `smartphone` (taxonomy class id **1**)
- **Open Images V7 source label:** `Mobile phone`
- **Requested (`--limit`):** 20
- **Exit code:** 0 (success; ends at `QA_PENDING`)

The `laptop` pilot (class id 0) was **not** re-run — it is protected and its
staging is never overwritten by this orchestrator.

---

## 2. Measured pilot counts (from real files / tool reports)

| Metric              | Value | Source of truth                                             |
| ------------------- | ----: | ----------------------------------------------------------- |
| requested           |    20 | the `--limit` asked                                         |
| downloaded          |     6 | image files present after the OID download                  |
| converted           |     6 | frozen converter `summary.images_converted`                 |
| conversion_errors   |     0 | frozen converter `reports/conversion_errors.json`           |
| valid_images        |     6 | frozen `ImageValidator` (Gate A): `total_images` − issues   |
| valid_annotations   |     6 | P4.2.2 annotation validator (Gate B): `total_labels` − issues |
| duplicates          |     0 | frozen `ImageValidator` exact-SHA-256 `duplicate_hashes`    |
| qa_pending          |     6 | converted images awaiting human QA                          |
| qa_accepted         |     0 | human-only; out of scope this sprint                        |
| qa_rejected         |     0 | human-only; out of scope this sprint                        |

**Why 6 and not 20:** the Open Images V7 `Mobile phone` train split returned only
6 images for this bounded request; the orchestrator reports the real count rather
than padding to the limit. Requesting 20 and receiving 6 is honest under-fill,
not a failure — all 6 converted and validated cleanly.

---

## 3. Staged output (isolated per-class directory)

```
dataset_acquisition/staging/openimages_smartphone_v1/
  images/       6 .jpg  (original OID stems preserved)
  labels/       6 .txt  (YOLO: class_id cx cy w h, 6-decimal precision)
  provenance/   provenance_manifest.json  (per-image SHA-256, dims, source)
  reports/      conversion_report.json, conversion_errors.json
```

- **Pairing:** 6 images ↔ 6 labels, matched 1:1 by original OID stem.
- **Class id in labels:** `1` (smartphone) — resolved dynamically from the frozen
  taxonomy, never hard-coded.
- **SHA-256 integrity:** verified — recomputing the hash of a staged image
  (`00e3bf5e2d0f4368.jpg`) reproduces the manifest value
  `62387dc6…ce231f2` exactly.
- **Conversion errors:** `error_count: 0`.

---

## 4. Safety / isolation verified

- **Pilot protected:** `openimages_laptop_v1/` and
  `openimages_laptop_canonical_v1/` were **not** modified by this run.
- **Frozen source untouched:** `scripts/convert_openimages_to_yolo.py`,
  `scripts/validate_annotations.py`, and `intelligence/device_ai/dataset/` show
  no git modifications.
- **No unreviewed data in `device_ai/datasets/`:** all output landed under
  `dataset_acquisition/staging/`; the frozen datasets dir is refused by guard.
- **Vendored toolkit pristine:** `OIDv4_ToolKit/` was not edited (see §6).

---

## 5. Licence / provenance posture

- Open Images **image** licences are **per-image Flickr licences that VARY and
  must be verified per image** — no redistribution right is claimed here.
- Open Images **box annotations** are **CC-BY-4.0 (Google)**.
- Each staged image carries a full provenance record (source, source class,
  canonical class, class id, SHA-256, width/height, conversion version +
  injected timestamp), so every image is traceable to its Open Images origin.

---

## 6. Environment blocker encountered and resolved (honest record)

The first real run **failed** with `OSError: [WinError 6] The handle is invalid`
raised inside the vendored `OIDv4_ToolKit/modules/downloader.py`, which calls
`os.get_terminal_size(0)` then `(1)` with no fallback when **both** stdio file
descriptors are pipes (the headless subprocess case). The orchestrator captured
the exact traceback, reported `DOWNLOAD_FAILED`, exited 1, and **fabricated no
results** — behaving exactly as specified.

Resolution: rather than edit the **untracked, vendored** toolkit (a change that
would be lost on any re-clone), the fix was made in code we own. `real_download`
now launches the toolkit through a tiny in-process shim that patches only that
single fragile call to degrade gracefully, then runs `main.py` verbatim via
`runpy`. The toolkit itself is left pristine. The re-run succeeded (§1–§3).

---

## 7. Classes covered

- **Real acquisition this run:** `smartphone` only (bounded pilot).
- **MAPPED, not yet acquired (8):** `tablet`, `monitor`, `television`, `printer`,
  `keyboard`, `mouse`, `camera`, `headphones` — remain `NOT_STARTED`.
- **Completed pilot (1):** `laptop` (`QA_PENDING`, P4.2.x; protected).
- **UNMAPPED / blocked (9):** `desktop`, `server`, `crt_monitor`, `router`,
  `power_supply`, `cable`, `game_console`, `smartwatch`, `battery` — never
  downloaded (no safe Open Images source).

---

## 8. QA status

`smartphone` = **`QA_PENDING`** (6 images). No image was auto-approved. Only a
human reviewer may advance a class to `QA_ACCEPTED`, and only `QA_ACCEPTED` data
may ever become a Dataset v1.0 candidate. **Dataset v1.0 is not released.**

---

## 9. Next steps (out of scope for this sprint)

- Human QA sign-off of the 6 `QA_PENDING` smartphone images.
- Bounded acquisition of the remaining 8 MAPPED classes, one at a time.
- A separate acquisition strategy for the 9 blocked classes.
- Dataset v1.0 assembly/split/freeze/release — governed separately.
