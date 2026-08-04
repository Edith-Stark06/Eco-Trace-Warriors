# Device Fingerprinting Engine — OpenCLIP + Verification (M1.5)

> The first **semantic visual fingerprinting** system in the Device Intelligence
> Engine: an OpenCLIP encoder replaces `MockEmbeddingEncoder` behind the extended
> `EmbeddingEncoder` interface, producing hash-backed **EcoTrace Fingerprints** with
> configurable similarity metrics and a match/no-match **Verification Engine** —
> **without changing the `/predict` API contract**.

**Module:** `intelligence/device_ai`
**Milestone:** M1.5 — Device Fingerprinting Engine
**Status:** implemented; real CLIP training/weights are operator-run (documented below)

---

## Table of contents

1. [Scope](#scope)
2. [Architecture](#architecture)
3. [Inference — `CLIPEncoder`](#inference--clipencoder)
4. [Fingerprint domain model](#fingerprint-domain-model)
5. [Similarity metrics](#similarity-metrics)
6. [Verification engine](#verification-engine)
7. [Persistence abstraction](#persistence-abstraction)
8. [Service orchestration](#service-orchestration)
9. [API surface](#api-surface)
10. [Guarded production swap](#guarded-production-swap)
11. [Configuration](#configuration)
12. [Testing](#testing)
13. [Integration guide](#integration-guide)
14. [Example requests & responses](#example-requests--responses)
15. [Backward compatibility](#backward-compatibility)
16. [Design rationale](#design-rationale)

---

## Scope

M1.5 adds **device fingerprinting** to the existing pipeline: semantic visual
embeddings, hash-backed identifiers, configurable similarity comparison, and a
verification engine for match/no-match decisions. Of the new `/fingerprint/*`
endpoints, all fields are **real** (no mocks); the existing `/predict` contract
is **unchanged** and backward-compatible.

| Component | Source in M1.5 |
|---|---|
| **`/fingerprint/generate`** | **real** — OpenCLIP encoder (when ready), hash-backed fingerprint, L2-normalized embedding |
| **`/fingerprint/compare`** | **real** — cosine/euclidean/manhattan similarity, threshold-based decision |
| **`/fingerprint/{eco_id}`** | **real** — stored fingerprint retrieval |
| `/predict` | **unchanged** — still returns `embedding_id`, backward-compatible |

**Explicitly out of scope**: OCR, blockchain anchoring, condition AI, material
intelligence, carbon intelligence. The CLIP encoder is **pluggable**: when
`open-clip-torch` is absent or no artifact resolves, the system degrades to the
deterministic `MockEmbeddingEncoder` (honest — never fakes an embedding).

## Architecture

The fingerprinting engine reuses the M1.2 preprocessing, M1.3 model registry,
and the M1.1 encoder interface (extended); nothing is duplicated.

```
                 ┌────────────── inference (fingerprinting) ───────────────┐
POST /fingerprint│ get_fingerprint_encoder()  ─ guarded selector ─┐        │
   /generate ───▶│   open-clip + artifact resolves + loads? ──────▶│ real   │
                 │   else ───────────────────────────────────────▶│ mock   │
                 │                                   CLIPEncoder / Mock      │
                 │                                        ↓                  │
                 │   FingerprintService ─ embed ─ normalize ─ hash ─┐      │
                 │                                                   ↓      │
                 │   DeviceFingerprint (frozen dataclass):                 │
                 │     eco_id, fingerprint (SHA-256), embedding,           │
                 │     encoder_name, encoder_version, metric, created_at   │
                 │                                                   ↓      │
                 │   FingerprintRepository (Protocol) ─ InMemory / JSON    │
                 └──────────────────────────────────────────────────────────┘

                 ┌────────────── comparison (verification) ────────────────┐
POST /fingerprint│   VerificationEngine(threshold, metric) ─ fetch left/  │
   /compare ────▶│     right from repository ─ compute_similarity() ─┐    │
                 │       similarity ≥ threshold? → MATCH : NO_MATCH   │    │
                 │   VerificationResult (similarity, distance, decision)   │
                 └──────────────────────────────────────────────────────────┘
```

Layering is unchanged (`api → inference/fingerprint → preprocessing →
utils/configs`). The encoder is an `inference/` adapter; the fingerprinting
domain lives in `fingerprint/` (models, similarity, verification, repository,
service).

## Inference — `CLIPEncoder`

`inference/clip_encoder.py` implements the extended
`inference/predictor.py::EmbeddingEncoder` contract (milestone M1.5 added
`embed()` alongside the existing `encode()`), so wiring it into the fingerprint
service (and therefore `/fingerprint/*`) is a dependency-injection concern only.

```python
class CLIPEncoder(EmbeddingEncoder):
    name = "clip"
    version = "openclip-{model_name.lower()}-1.0.0"

    def __init__(self, *, weights_path: Path | None = None,
                 model_name: str = "ViT-B-32",
                 pretrained: str = "laion2b_s34b_b79k",
                 dimension: int = 512, device: str | None = None,
                 encode_fn: EncodeFn | None = None) -> None: ...

    @property
    def is_ready(self) -> bool: ...          # True only when a model is loaded

    def embed(self, images: list[LoadedImage]) -> EmbeddingVector: ...
    def encode(self, images: list[LoadedImage]) -> EmbeddingResult: ...
```

Flow of `embed()`:

1. Guard: if no model is loaded, raise `EncoderNotReadyError` (honest — never
   fakes an embedding).
2. Run OpenCLIP `model.encode_image(batch)` over `[preprocess(img.image) for
   img in images]` (Pillow → tensor via the model's transform), with
   `torch.no_grad()`.
3. Move to CPU (`.cpu()`), mean-pool per-image embeddings into a single vector,
   L2-normalize → unit length.
4. Return `EmbeddingVector(values, dimension, normalized=True)`.

**Loading** (`weights_path` given, `encode_fn` not injected): `_resolve_weights`
accepts a direct `.bin`/`.pt` file or a directory containing
`open_clip_pytorch_model.bin` / `model.pt`. Loading is import-guarded and
**degrades to not-ready** (returns `None`, never raises) when the artifact is
absent, `open-clip-torch` is missing, or the load fails — so the caller can fall
back to the mock.

**Everything is injectable.** Passing `encode_fn=<fake>` bypasses disk/torch
entirely, which is how the whole aggregate/normalize path is unit-tested in the
base environment (`tests/test_clip_encoder.py`).

## Fingerprint domain model

`fingerprint/models.py` — `DeviceFingerprint`, the canonical, storage-agnostic
record the engine produces:

```python
@dataclass(frozen=True, slots=True)
class DeviceFingerprint:
    eco_id: str                       # ET-YYYY-XXXXXXXX
    fingerprint: str                   # SHA-256 hex of the normalized embedding
    embedding: tuple[float, ...]       # L2-normalized vector
    dimension: int
    encoder_name: str                  # "clip"
    encoder_version: str               # "openclip-vit-b-32-1.0.0"
    metric: str                        # default similarity metric ("cosine")
    created_at: datetime               # UTC timestamp
    source_hashes: tuple[str, ...] = () # SHA-256 of source images (provenance)
    device_type: str = ""              # optional (from detection, reused)
    brand: str = ""                    # optional (from detection, reused)

    def to_dict(self) -> dict[str, object]: ...
    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DeviceFingerprint: ...
```

The **hash-backed fingerprint** is a stable identifier derived from the
rounded, canonical-encoded normalized embedding:

```python
def compute_fingerprint(embedding: tuple[float, ...], *, precision: int = 6) -> str:
    """Return the SHA-256 hex digest of the canonical encoding."""
    canonical = ",".join(f"{v:.{precision}f}" for v in embedding).encode("utf-8")
    return hash_bytes(canonical)  # SHA-256
```

Rounding to 6 decimals makes the fingerprint **robust to sub-precision float
noise** while preserving discriminative power. Identical embeddings (within
precision) always hash to the same 64-character hex string.

## Similarity metrics

`fingerprint/similarity.py` — three configurable metrics, all normalized to
`[0, 1]` where `1.0` = identical:

| Metric | Formula | Similarity | Distance |
|---|---|---|---|
| **Cosine** | `(1 + cos θ) / 2` | `similarity` | `1 - cos θ` |
| **Euclidean** | `1 / (1 + L2)` | `similarity` | L2 distance |
| **Manhattan** | `1 / (1 + L1)` | `similarity` | L1 distance |

```python
class SimilarityMetric(str, Enum):
    COSINE = "cosine"
    EUCLIDEAN = "euclidean"
    MANHATTAN = "manhattan"

def compute_similarity(
    a: Vector, b: Vector, metric: str | SimilarityMetric = SimilarityMetric.COSINE
) -> SimilarityScore:
    """Compare two vectors using the named metric."""
    ...

@dataclass(frozen=True, slots=True)
class SimilarityScore:
    metric: SimilarityMetric
    similarity: float   # in [0, 1], 1.0 = identical
    distance: float     # raw geometric distance (lower = more similar)
```

Implementations are **pure Python** (math.fsum, no NumPy) so the whole engine
runs in the base environment. Zero vectors are handled (cosine → 0.0
similarity). All metrics are **symmetric** and **monotonic** (nearer vectors
score higher).

## Verification engine

`fingerprint/verification.py` — compares two fingerprints and decides
match/no-match against a threshold:

```python
class VerificationEngine:
    def __init__(self, *, threshold: float, metric: str | SimilarityMetric = SimilarityMetric.COSINE): ...

    def verify(self, left: DeviceFingerprint, right: DeviceFingerprint,
               *, metric: str | SimilarityMetric | None = None) -> VerificationResult: ...

@dataclass(frozen=True, slots=True)
class VerificationResult:
    metric: SimilarityMetric
    similarity: float
    distance: float
    threshold: float
    decision: VerificationDecision  # MATCH | NO_MATCH
    left_eco_id: str
    right_eco_id: str

    @property
    def is_match(self) -> bool: ...
```

Decision rule: `similarity >= threshold` → `MATCH`, else `NO_MATCH`. The
threshold and default metric are injected (from settings), and a per-call metric
override is supported.

## Persistence abstraction

`fingerprint/repository.py` — storage-agnostic persistence via a `Protocol`:

```python
@runtime_checkable
class FingerprintRepository(Protocol):
    def save(self, fingerprint: DeviceFingerprint) -> None: ...
    def get(self, eco_id: str) -> DeviceFingerprint | None: ...
    def exists(self, eco_id: str) -> bool: ...
    def list_ids(self) -> list[str]: ...
```

Two implementations ship with M1.5:

- **`InMemoryFingerprintRepository`** — process-local dict; the default and the
  one used throughout the test suite. Records are lost when the process exits.
- **`JsonFileFingerprintRepository`** — one JSON document per EcoID under a
  configured directory (default `fingerprints/`). Durable across restarts and
  human-inspectable.

The service depends only on the `Protocol`, so the storage medium (in-memory, a
JSON file tree, a future vector database or blockchain anchor) can change
without touching the domain or API layers (`CLAUDE.md` → "persistence
abstraction; do not tightly couple to storage").

## Service orchestration

`fingerprint/service.py` — `FingerprintService`, the single collaborator the API
layer depends on:

```python
class FingerprintService:
    def __init__(self, *, encoder: EmbeddingEncoder,
                 repository: FingerprintRepository,
                 ecoid_generator: EcoIDGenerator,
                 verifier: VerificationEngine,
                 clock: Callable[[], datetime] = _utc_now) -> None: ...

    def generate(self, images: list[LoadedImage], *, device_type: str = "",
                 brand: str = "", persist: bool = True) -> DeviceFingerprint: ...

    def get(self, eco_id: str) -> DeviceFingerprint: ...

    def compare(self, left_eco_id: str, right_eco_id: str,
                *, metric: str | SimilarityMetric | None = None) -> VerificationResult: ...

    def compare_images(self, left_images: list[LoadedImage],
                       right_images: list[LoadedImage],
                       *, metric: str | SimilarityMetric | None = None) -> VerificationResult: ...
```

- `generate()` — embed images, defensively re-normalize (the guard keeps the
  fingerprint hash well-defined regardless of encoder), compute the hash-backed
  fingerprint, build `DeviceFingerprint`, persist (unless `persist=False`).
- `get()` — fetch a stored fingerprint (or raise `FingerprintNotFoundError`).
- `compare()` — verify two stored fingerprints by EcoID.
- `compare_images()` — verify two ad-hoc image batches without persisting them.

Every collaborator (encoder, repository, EcoID generator, verifier, clock) is
injected, so the whole engine is exercised deterministically in tests with a
mock encoder and an in-memory repository — no trained weights, no filesystem.

## API surface

`api/fingerprint_routes.py` — three endpoints under `/fingerprint`:

### `POST /fingerprint/generate`

`multipart/form-data`. Field **`images`**: 1–6 files (same validation as
`/predict`). Optional form fields: `device_type`, `brand` (recorded for
provenance).

**Returns:** `FingerprintResponse` (eco_id, fingerprint, embedding,
dimension, encoder_name, encoder_version, metric, created_at, source_hashes,
device_type, brand).

### `POST /fingerprint/compare`

JSON body: `{ "left_eco_id": "...", "right_eco_id": "...", "metric": "cosine" }`
(metric is optional; defaults to the service's configured metric).

**Returns:** `CompareResponse` (left_eco_id, right_eco_id, metric, similarity,
distance, threshold, decision, is_match).

### `GET /fingerprint/{eco_id}`

**Returns:** `FingerprintResponse` for the stored fingerprint.

**Errors:** `404` with `FINGERPRINT_NOT_FOUND` when the EcoID is unknown.

## Guarded production swap

`api/dependencies.py::get_fingerprint_encoder()` chooses the encoder at process
start (cached singleton). `_build_clip_encoder(settings)` resolves
`clip_weights` (relative to `model_dir` unless absolute) and constructs a
`CLIPEncoder`. Construction never raises; the selection rule is:

```
encoder = _build_clip_encoder(settings)
if encoder is not None and encoder.is_ready:   # open-clip + artifact + load ok
    return encoder                              # real CLIP
else:
    return MockEmbeddingEncoder()               # honest fallback
```

Both produce **identical** `EmbeddingVector` shapes (unit-length tuple), so the
swap is invisible to the service — and CI / the base environment (no
open-clip-torch, no weights) stay green on the mock path. This mirrors the M1.4
honesty pattern for the detector.

## Configuration

Additive, backwards-compatible env vars (defaults keep the mock path):

| Variable | Default | Description |
|---|---|---|
| `CLIP_MODEL_NAME` | `ViT-B-32` | OpenCLIP architecture name (e.g. `ViT-B-32`, `ViT-L-14`). |
| `CLIP_PRETRAINED` | `laion2b_s34b_b79k` | OpenCLIP pretrained-weights tag used when no local artifact resolves. |
| `CLIP_WEIGHTS` | `clip` | Artifact locator (file/dir under `MODEL_DIR`, or absolute). Absent/unloadable → mock fallback. |
| `FINGERPRINT_METRIC` | `cosine` | Default similarity metric (`cosine` \| `euclidean` \| `manhattan`). |
| `FINGERPRINT_MATCH_THRESHOLD` | `0.85` | Similarity (0..1) at or above which two fingerprints are judged a match. |
| `FINGERPRINT_STORE_DIR` | `fingerprints` | Directory for the JSON fingerprint backend (relative to cwd). |
| `FINGERPRINT_BACKEND` | `memory` | Fingerprint persistence backend (`memory` \| `json`). |

## Testing

All M1.5 tests run in the **base environment** (no torch/open-clip-torch) via
injected fakes. From `intelligence/device_ai`:

```bash
pytest tests/test_similarity.py \
       tests/test_fingerprint_models.py \
       tests/test_verification.py \
       tests/test_repository.py \
       tests/test_fingerprint_service.py \
       tests/test_clip_encoder.py \
       tests/test_fingerprint_routes.py -q
```

- `test_similarity.py` — metric correctness (identical → 1.0, orthogonal cosine
  → 0.5, symmetry, monotonicity, formulas).
- `test_fingerprint_models.py` — determinism of hash-backed fingerprint,
  canonical encoding, eco_id format, to_dict/from_dict round-trip.
- `test_verification.py` — MATCH/NO_MATCH around threshold, dimension mismatch
  raises, metric override.
- `test_repository.py` — InMemory + JsonFile round-trip, exists, list_ids,
  missing → None, path-traversal guard.
- `test_fingerprint_service.py` — generate→persist→get, compare by eco_id,
  compare_images, determinism, not-found.
- `test_clip_encoder.py` — not-ready degradation when backend absent (injected
  `encode_fn`), aggregation/normalization.
- `test_fingerprint_routes.py` — 3 endpoints happy-path + 404 + validation
  errors; envelope shape; **`/predict` still passes** (backward-compat
  assertion).

## Integration guide

To integrate a **real OpenCLIP encoder** (replace the mock):

1. Install the optional model dependencies (a machine with a GPU is recommended
   for fine-tuning):

   ```bash
   cd intelligence/device_ai
   source .venv/bin/activate                 # Windows: .venv\Scripts\activate
   pip install -r requirements-models.txt    # open-clip-torch, torch
   ```

2. Train or download an OpenCLIP model. To train from scratch, use the
   `open_clip` training scripts (outside this repo) over a device-photo dataset.
   To use a pre-trained model, download it from the OpenCLIP registry (e.g.
   `laion2b_s34b_b79k`).

3. Place the artifact under `MODEL_DIR` (default `models/`) in a subdirectory
   named `clip/` (or any name resolvable via `CLIP_WEIGHTS`), as either
   `open_clip_pytorch_model.bin` or `model.pt`.

   Example layout:
   ```
   models/
   └── clip/
       └── open_clip_pytorch_model.bin   # or model.pt
   ```

4. Set environment variables:
   ```bash
   export CLIP_MODEL_NAME=ViT-B-32        # or ViT-L-14, etc.
   export CLIP_PRETRAINED=laion2b_s34b_b79k  # or your custom tag
   export CLIP_WEIGHTS=clip               # points to models/clip/
   ```

5. Restart the service. `get_fingerprint_encoder()` loads the real CLIP model
   on next start; `/fingerprint/*` endpoints now use genuine semantic embeddings.

**No code changes required** — the encoder is swapped via dependency injection.

## Example requests & responses

### Generate a fingerprint

```bash
curl -X POST http://localhost:8100/fingerprint/generate \
  -F "images=@device_front.jpg" \
  -F "images=@device_back.jpg" \
  -F "device_type=Laptop" \
  -F "brand=Dell"
```

**Response `200`:**

```json
{
  "eco_id": "ET-2026-1A2B3C4D",
  "fingerprint": "a3f5e8d2c1b4f6e9a7d3c5b8f1e4d7c2a9b6f3e5d8c1a4f7e2d9b5c8f6e3a1d4",
  "embedding": [0.123, -0.456, 0.789, ...],  // 512 values
  "dimension": 512,
  "encoder_name": "clip",
  "encoder_version": "openclip-vit-b-32-1.0.0",
  "metric": "cosine",
  "created_at": "2026-08-01T12:00:00Z",
  "source_hashes": [
    "d4e5f6a7b8c9d1e2f3a4b5c6d7e8f9a1b2c3d4e5f6a7b8c9d1e2f3a4b5c6d7e8",
    "f9a1b2c3d4e5f6a7b8c9d1e2f3a4b5c6d7e8f9a1b2c3d4e5f6a7b8c9d1e2f3a4"
  ],
  "device_type": "Laptop",
  "brand": "Dell"
}
```

### Compare two fingerprints

```bash
curl -X POST http://localhost:8100/fingerprint/compare \
  -H 'Content-Type: application/json' \
  -d '{
    "left_eco_id": "ET-2026-1A2B3C4D",
    "right_eco_id": "ET-2026-5E6F7A8B",
    "metric": "cosine"
  }'
```

**Response `200`:**

```json
{
  "left_eco_id": "ET-2026-1A2B3C4D",
  "right_eco_id": "ET-2026-5E6F7A8B",
  "metric": "cosine",
  "similarity": 0.92,
  "distance": 0.16,
  "threshold": 0.85,
  "decision": "match",
  "is_match": true
}
```

### Retrieve a stored fingerprint

```bash
curl http://localhost:8100/fingerprint/ET-2026-1A2B3C4D
```

**Response `200`:** (same shape as `generate`)

**Response `404`:**

```json
{
  "success": false,
  "error": {
    "code": "FINGERPRINT_NOT_FOUND",
    "message": "No fingerprint found for the given EcoID.",
    "details": { "eco_id": "ET-2026-DEADBEEF" }
  },
  "request_id": "a1b2c3d4e5f6"
}
```

## Backward compatibility

The existing `/predict` contract is **completely unchanged**. M1.5 added the
`embed()` method to the `EmbeddingEncoder` interface alongside the existing
`encode()`, and provided a default `encode()` implementation on the ABC that
derives its `embedding_id` from `embed()` — so a single `embed()` override
powers both.

**`MockEmbeddingEncoder` preserved its deterministic `embedding_id` behaviour**
(`mock_embedding_XXXXXXXX`) by overriding `encode()` separately, so existing
`/predict` tests stay green and the prediction contract is byte-compatible.

The new `/fingerprint/*` endpoints are an **additive** surface mounted under a
separate prefix — `/predict` is unaware of fingerprinting.

## Design rationale

**Why extend the encoder interface instead of adding a separate fingerprint
encoder?** The semantic embedding is the *same* learned representation whether
it's surfaced as an opaque `embedding_id` (for `/predict`) or as the full
normalized vector (for fingerprinting). Duplicating the encoder would duplicate
the artifact, the model loading, and the inference pass — exactly the
duplication the sprint (and `CLAUDE.md`) forbids. So M1.5 extends
`EmbeddingEncoder` to expose the vector via `embed()` while keeping `encode()`
backward-compatible.

**Why a storage-agnostic `FingerprintRepository` Protocol?** The sprint spec
mandates "do not tightly couple to storage" (`CLAUDE.md` → persistence
abstraction). A Protocol (structural subtyping) lets the storage medium (in-memory,
JSON, a future vector database or blockchain anchor) change without touching the
domain or API layers. The service depends only on the Protocol, never on a
concrete store.

**Why hash-backed fingerprints?** A stable, content-derived identifier (SHA-256
of the rounded, canonical embedding) is the foundation for de-duplication,
similarity search, and blockchain anchoring in future milestones. Two devices
with identical embeddings (within precision) always share the same fingerprint
hash, enabling exact-match lookups before similarity comparison.

**Why dependency-inject the encoder/factory?** The heavy backend
(open-clip-torch/torch/GPU) is absent in CI and the base environment. Injecting
a loaded `encode_fn` (CLIP) or the mock lets every unit of
pooling/normalization/verification logic be tested deterministically with tiny
fakes, while the real backend paths are marked `# pragma: no cover`.

---

_Part of **EcoTrace India** — IEEE YESIST 2026. See the module
[`README.md`](../../README.md), [`training/README.md`](../../training/README.md)
and the platform-wide `docs/engineering/` standards._
