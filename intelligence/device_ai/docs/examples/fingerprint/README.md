# Example fingerprint artifacts (M1.5)

These files are **illustrative** outputs of the Device Fingerprinting Engine,
checked in for reference. They are generated from the deterministic
`MockEmbeddingEncoder` — **no real CLIP model is trained, downloaded or
executed** (the base environment has neither `open-clip-torch` nor torch). The
embeddings are the mock's deterministic pseudo-vectors, standing in for a real
OpenCLIP encoder; the response *shapes* are exactly what the live endpoints
return.

| File | Produced by | Live endpoint equivalent |
|---|---|---|
| `generate_response.json` | `FingerprintService.generate` → `DeviceFingerprint.to_dict` | `POST /fingerprint/generate` |
| `compare_response.json` | `FingerprintService.compare` → `VerificationResult` | `POST /fingerprint/compare` |
| `similarity_report.json` | `compute_similarity` across every metric | (evaluation, not an endpoint) |
| `similarity_report.md` | Markdown rendering of `similarity_report.json` | (evaluation, not an endpoint) |

## Regenerating

The artifacts are **byte-stable** — the generator injects a fixed clock
(`2026-08-01T12:00:00Z`), *sequential* EcoIDs (`ET-2026-00000001`, …) and the
mock encoder's deterministic embeddings. To regenerate them, from
`intelligence/` with `PYTHONPATH=.`:

```bash
python -m device_ai.scripts.gen_fingerprint_examples
```

## What the examples show

- **`generate_response.json`** — the full fingerprint record for one device: the
  public `eco_id`, the hash-backed `fingerprint` (64-char SHA-256 hex), the
  L2-normalized `embedding` (512 floats), the `encoder_name`/`encoder_version`,
  the default `metric`, `created_at`, the `source_hashes` (image provenance) and
  the optional `device_type`/`brand`.
- **`compare_response.json`** — a verification of two **distinct** devices:
  cosine `similarity ≈ 0.51` is well below the `0.85` threshold, so the
  `decision` is `no_match`. Comparing a fingerprint with itself scores `1.0`
  (`match`).
- **`similarity_report.{json,md}`** — a **similarity evaluation** across all
  three metrics (cosine, euclidean, manhattan) over a small synthetic device
  set. Each metric's full pairwise matrix shows the diagonal (same device →
  `1.0`) versus the off-diagonal inter-device scores, illustrating the
  separation a match threshold is chosen from. Note the mock embeddings are
  pseudo-random, so inter-device similarity clusters near a metric-dependent
  baseline (cosine ≈ 0.5 for near-orthogonal vectors); a **real** CLIP encoder
  produces semantically meaningful separation (visually similar devices score
  high, dissimilar ones low).

The full engine, interface, similarity formulas, verification rules, persistence
abstraction and integration guide are documented in
[`docs/engineering/fingerprint.md`](../../engineering/fingerprint.md).
