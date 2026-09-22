# Open Images → EcoTrace Laptop Pilot — Human QA Sign-Off Package

Status: Manual-review checkpoint (**PILOT_REVIEW_REQUIRED**) — reviewer package assembled, **nothing certified, nothing released**
Sprint: P4.2.5 — Laptop pilot human QA sign-off package
Scope: `laptop` class only — the 7 outstanding items of the 20-image canonical candidate
Audience: annotation reviewers, QA leads (human sign-off required)

---

> **What this report is.** It is the *human reviewer package* for the Laptop
> canonical candidate (`openimages_laptop_canonical_v1`), whose pilot status is
> `PILOT_REVIEW_REQUIRED`. It surfaces every item the P4.2.4 remediation left
> `PENDING_REVIEW` (or proposed for exclusion) with the visual and
> machine-readable evidence a human needs to decide, and it does **nothing
> else**. It **certifies nothing**: every item below is `PENDING_REVIEW`, the
> `Human Decision` column is deliberately blank, and no `PENDING_REVIEW` /
> `REVIEW_PENDING` was changed to `ACCEPTED`. It does **not** declare the pilot
> ready for scale, and it does **not** change the existing QA policy.

> **Non-destruction guarantee (proven, not asserted).** The generator is
> strictly read-only on both the immutable Open Images source
> (`openimages_laptop_v1/`) and the canonical candidate
> (`openimages_laptop_canonical_v1/`). It writes **only** under
> `dataset_acquisition/review/openimages_laptop_human_qa_signoff_v1/`, which
> lives outside the immutable source. A SHA-256 snapshot of the source *and*
> canonical images+labels is taken before and after rendering and compared; the
> comparison is recorded in `integrity_verification.json`
> (`all_unchanged: true`, 42 source + 40 canonical files checked). No metric is
> invented — blur numbers come from the frozen
> `device_ai.dataset.metadata.blur_score` against the frozen blur threshold
> (`100.0`).

> **How to reproduce.** From the repository root:
> ```
> python scripts/build_laptop_qa_signoff.py
> ```
> All inputs default to the Laptop pilot; the only timestamp is injected
> (`--signoff-timestamp`, default `2026-08-09T00:00:00+00:00`), so identical
> inputs produce byte-identical machine-readable artifacts. Artifacts land under
> `dataset_acquisition/review/openimages_laptop_human_qa_signoff_v1/`.

---

## 1. Reviewer sign-off table

Fill **`Human Decision`** by hand with one of `ACCEPTED` / `REJECTED` (the
machine-readable equivalent in `signoff_template.json` uses the vocabulary
`PENDING_REVIEW` → `ACCEPTED` / `REJECTED`). `Proposed Decision` is the
tooling's non-binding suggestion; it is **not** a decision. All rows start
`PENDING_REVIEW`.

| ID | Issue | Evidence | Proposed Decision | Human Decision | Reviewer | Date | Notes |
| -- | ----- | -------- | ----------------- | -------------- | -------- | ---- | ----- |
| QA01 | Borderline low-light blur (45.6, lowest in set); laptop identifiable, box correct. Held — no authority to auto accept/reject a below-threshold blur. | `previews/qa01_original.jpg`, `previews/qa01_corrected.jpg` | Confirm keep as difficult sample, or reject |  |  |  |  |
| QA03 | Source group box covers a whole row of distinct laptops (violates one-box-per-instance). Proposed split into 5 per-laptop boxes; flagged difficult. | `previews/qa03_before_after.jpg` | ACCEPT corrected split (5 boxes) |  |  |  |  |
| QA04 | Source omits the prominent open sticker-covered laptop (centre-right). Proposed 1 added box; the 5 source boxes preserved. | `previews/qa04_before_after.jpg` | ACCEPT corrected add-instance (6 boxes) |  |  |  |  |
| QA14 | Blurry (58.7) extreme keyboard macro, no laptop form factor visible; indistinguishable from the `keyboard` class. Proposed exclusion. | `previews/qa14_original.jpg` | EXCLUDE (confirm) |  |  |  |  |
| QA15 | Source box spans full frame height incl. cat paws + wall (~half non-laptop). Proposed tightened box to screen bezel + truncated MacBook only. | `previews/qa15_before_after.jpg` | ACCEPT tightened box |  |  |  |  |
| QA17 | Below-threshold blur (59.96) — Gate A difficult-sample sign-off required. | `previews/qa17_original.jpg`, `previews/qa17_corrected.jpg` | Confirm difficult-sample sign-off, or reject |  |  |  |  |
| QA18 | Below-threshold blur (77.04) — Gate A difficult-sample sign-off required. | `previews/qa18_original.jpg`, `previews/qa18_corrected.jpg` | Confirm difficult-sample sign-off, or reject |  |  |  |  |

## 2. Per-item evidence detail

Every fact below is drawn verbatim from
`openimages_laptop_human_qa_signoff_v1/evidence.json`. Coordinates are given in
both the normalised YOLO `cx cy w h` form (as stored on disk) and pixel-space
`x1 y1 x2 y2`. The `Source SHA-256` is the frozen `sha256_hash` of the source
image bytes (also recorded in the frozen `remediation_manifest.json`).

### QA01 — held REVIEW_PENDING (annotation unchanged)

| Field | Value |
| ----- | ----- |
| Source image | `00767fb6565581c6.jpg` (768 × 1024) |
| Canonical image | `laptop_openimages_000001.jpg` |
| Source SHA-256 | `805e3223e5e3583a7cfc9bf8f7bdca7368c7187a76e5958c29a748ac6de9d6a6` |
| Blur score | 45.55 (**below** threshold 100.0) |
| Object count | 1 → 1 (unchanged) |
| Kind | `review_hold` |

The annotation is byte-identical to the source (original == corrected); only the
blur is at issue. Box: `0.626667 0.211250 0.743333 0.422500` → px
`195.84 0.00 766.72 432.64`.

### QA03 — re-annotate: split group box into 5 instances

| Field | Value |
| ----- | ----- |
| Source image | `0171ad35f1651698.jpg` (1024 × 768) |
| Canonical image | `laptop_openimages_000003.jpg` |
| Source SHA-256 | `4fcc4f0be859f0fba59b29f9eb02853ca3668feae782c7c6bbab7589201d78ec` |
| Blur score | 348.38 (above threshold) |
| Object count | 1 → 5 |
| Kind | `reannotation` |

Original (1 box), normalised → pixel:
- `0.286133 0.657552 0.572266 0.682292` → `0.00 243.00 586.00 767.00`

Corrected (5 boxes), normalised → pixel:
- `0.131836 0.695312 0.263672 0.609375` → `0.00 300.00 270.00 768.00`
- `0.239258 0.533854 0.185547 0.338542` → `150.00 280.00 340.00 540.00`
- `0.361328 0.491536 0.136719 0.240885` → `300.00 285.00 440.00 470.00`
- `0.444336 0.462240 0.107422 0.195312` → `400.00 280.00 510.00 430.00`
- `0.512695 0.452474 0.126953 0.162760` → `460.00 285.00 590.00 410.00`

### QA04 — re-annotate: add 1 missing instance (5 source boxes preserved)

| Field | Value |
| ----- | ----- |
| Source image | `14587a599414300c.jpg` (1024 × 683) |
| Canonical image | `laptop_openimages_000004.jpg` |
| Source SHA-256 | `41a5bf97eea6d2c4a9d86d9d1f5579a894e50bd9df55c0b9668db8cd296f1ea5` |
| Blur score | 365.69 (above threshold) |
| Object count | 5 → 6 |
| Kind | `reannotation` |

The five source boxes are preserved verbatim; one box is appended for the
missing centre-right open laptop. Added box (6th), normalised → pixel:
- `0.583496 0.483163 0.200195 0.219619` → `495.00 255.00 700.00 405.00`

### QA14 — proposed exclusion (no corrected annotation)

| Field | Value |
| ----- | ----- |
| Source image | `79182035199f2b58.jpg` (1024 × 1024) |
| Canonical image | *(none — proposed for exclusion)* |
| Source SHA-256 | `275c18b4bfc6c54eaaba25798a5f0a40d5922208d99f7838f3fa47cb1bc3bcaf` |
| Blur score | 58.69 (**below** threshold 100.0) |
| Object count | 1 → *(n/a)* |
| Kind | `exclusion` |

No "corrected" annotation is fabricated — the item carries **only** an
`original` preview. The source image remains byte-identical in the immutable
source staging. Original box: `0.499219 0.499219 0.998438 0.998438`.

### QA15 — re-annotate: tighten loose full-frame box

| Field | Value |
| ----- | ----- |
| Source image | `936a6d462e9d4873.jpg` (1024 × 768) |
| Canonical image | `laptop_openimages_000014.jpg` |
| Source SHA-256 | `c42badcd2443da8948b49088519069b9065042946af9e1bd3db4b1fee1f1c305` |
| Blur score | 220.25 (above threshold) |
| Object count | 1 → 1 (geometry tightened) |
| Kind | `reannotation` |

Original → pixel: `0.212110 0.500521 0.424219 0.996875` → `0.00 1.60 434.40 767.20`.
Corrected → pixel: `0.205078 0.570312 0.410156 0.859375` → `0.00 108.00 420.00 768.00`
(top raised to the screen bezel, right edge pulled in).

### QA17 — Gate A difficult-sample sign-off (blur)

| Field | Value |
| ----- | ----- |
| Source image | `bc3873e0c9ada07c.jpg` (1024 × 768) |
| Canonical image | `laptop_openimages_000016.jpg` |
| Source SHA-256 | `6cf4bb8ceb0f16cde18acba3094a59330a11ab31abd5a72b34357583ddb27559` |
| Blur score | 59.96 (**below** threshold 100.0) |
| Object count | 1 → 1 (unchanged) |
| Kind | `blur_gate_a` |

Annotation unchanged; surfaced because the canonical image still trips the
frozen blur threshold in `validation/image_validation_strict.json`.

### QA18 — Gate A difficult-sample sign-off (blur)

| Field | Value |
| ----- | ----- |
| Source image | `ca77666f682b922f.jpg` (1024 × 680) |
| Canonical image | `laptop_openimages_000017.jpg` |
| Source SHA-256 | `ee877fe534c3c06faff9d42e99320b79d19f40754b46f949ac4a790539f4b65a` |
| Blur score | 77.04 (**below** threshold 100.0) |
| Object count | 1 → 1 (unchanged) |
| Kind | `blur_gate_a` |

Annotation unchanged; surfaced because the canonical image still trips the
frozen blur threshold in `validation/image_validation_strict.json`.

---

## 3. Package artifacts

Under `dataset_acquisition/review/openimages_laptop_human_qa_signoff_v1/`:

| Artifact | Purpose |
| -------- | ------- |
| `previews/` | Annotated before/after JPEG evidence (orange `src#` = original, green `fix#` = corrected). Re-annotations get an `*_before_after.jpg`; the exclusion gets only an `*_original.jpg`. |
| `evidence.json` | One entry per item: exact source + canonical filename, source SHA-256, original/corrected object counts, and original vs corrected annotation coordinates (normalised + pixel). |
| `signoff_template.json` | Machine-readable sign-off; every row `status: PENDING_REVIEW` with empty `human_decision` / `reviewer` / `date`. Allowed statuses: `PENDING_REVIEW`, `ACCEPTED`, `REJECTED`. |
| `integrity_verification.json` | Before/after SHA-256 snapshot proof (`all_unchanged: true`). |

Cross-reference: the frozen manifests this package reads are
`openimages_laptop_canonical_v1/reports/remediation_manifest.json` and
`.../validation/image_validation_strict.json`; the upstream visual-QA verdict is
`docs/ai/reports/openimages_laptop_pilot_visual_qa.md` and the remediation
record is `docs/ai/reports/openimages_laptop_pilot_remediation.md`.

---

## 4. What this package does NOT do

- It does **not** certify the pilot or declare `PILOT_READY_FOR_SCALE`.
- It does **not** change any `PENDING_REVIEW` / `REVIEW_PENDING` to `ACCEPTED`.
- It does **not** modify any source or canonical image or label (proven by
  `integrity_verification.json`).
- It does **not** invent a quality/accuracy metric or a new threshold.
- It does **not** train anything, download anything, or touch another class.

Pilot status remains `PILOT_REVIEW_REQUIRED` until a human records decisions in
the table above and in `signoff_template.json`.

