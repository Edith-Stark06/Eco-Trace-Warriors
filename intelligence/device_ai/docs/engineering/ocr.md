# OCR Intelligence Engine — EasyOCR + Barcode Decoding + Parser (M1.6)

> The first **printed-identity extraction** system in the Device Intelligence
> Engine: a pluggable EasyOCR text backend and OpenCV barcode/QR reader feed a
> pure **normalization/parser layer** that turns noisy OCR spans into structured,
> confidence-scored identity fields — manufacturer, model, serial number, IMEI,
> MAC address, QR and barcode — **without changing the `/predict` API contract**.

**Module:** `intelligence/device_ai`
**Milestone:** M1.6 — OCR Intelligence Engine
**Status:** implemented; real EasyOCR/OpenCV are operator-run serving-only
plug-ins (documented below), degrading honestly to deterministic mocks

---

## Table of contents

1. [Scope](#scope)
2. [Architecture](#architecture)
3. [Domain models](#domain-models)
4. [Patterns & normalization](#patterns--normalization)
5. [Parser](#parser)
6. [Text backends](#text-backends)
7. [Barcode/QR reader](#barcodeqr-reader)
8. [Service orchestration](#service-orchestration)
9. [API surface](#api-surface)
10. [Guarded production swap](#guarded-production-swap)
11. [Configuration](#configuration)
12. [Optional fingerprint-identity seam](#optional-fingerprint-identity-seam)
13. [Testing](#testing)
14. [Integration guide](#integration-guide)
15. [Example requests & responses](#example-requests--responses)
16. [Backward compatibility](#backward-compatibility)
17. [Design rationale](#design-rationale)

---

## Scope

M1.6 adds **OCR-based identity extraction** to the engine: text recognition,
QR/barcode decoding, and a normalization layer that produces structured,
confidence-scored fields. It reuses the M1.2 preprocessing
(`image_loader`/`validator`), the settings/DI/exception/router patterns, the
`MODEL_DIR` artifact-locator convention (as CLIP used) and the hashing utils —
nothing is duplicated. It is exposed via new `/ocr/*` endpoints plus an
optional, backward-compatible identity seam into the M1.5 fingerprint engine.

| Component | Source in M1.6 |
|---|---|
| **`POST /ocr/extract`** | **real** — EasyOCR text (when ready) + OpenCV barcode/QR (when ready), normalized to structured fields |
| **`POST /ocr/parse`** | **real** — the pure normalization layer over client-supplied spans/barcodes (no image, no backend) |
| **`GET /ocr/fields`** | **real** — the supported `FieldType` discovery list |
| `/predict` | **unchanged** — still returns `ocr: {serial_number, model}`, byte-compatible |

**Explicitly out of scope**: blockchain, condition AI, material intelligence,
carbon intelligence. Both the text backend and the barcode reader are
**pluggable**: when `easyocr` / `opencv-python-headless` are absent or no
artifact resolves, the engine degrades to the deterministic `MockOCRBackend` /
`MockBarcodeReader` (honest — never fakes a read).

The existing `inference.predictor.OCREngine`/`MockOCREngine` (bound to the
frozen `/predict` serial+model envelope) are **left untouched**; M1.6 is a
richer, separate subsystem, mirroring how M1.5 added `fingerprint/` rather than
overloading `/predict`.

## Architecture

The OCR engine reuses the M1.2 preprocessing and the M1.1 settings/DI/exception
patterns; nothing is duplicated.

```
              ┌──────────────────── OCR Intelligence Engine ────────────────────┐
POST /ocr     │ get_ocr_backend()   ─ guarded selector ─┐                        │
   /extract ─▶│   easyocr + artifact resolves + loads? ─▶│ EasyOCRBackend (real) │
              │   else ────────────────────────────────▶│ MockOCRBackend        │
              │ get_barcode_reader()─ guarded selector ─┐                        │
              │   cv2 present + detectors build? ───────▶│ OpenCVBarcodeReader   │
              │   else ────────────────────────────────▶│ MockBarcodeReader     │
              │                                          ↓                        │
              │   spans : list[TextSpan]   barcodes : list[BarcodeResult]        │
              │                                          ↓                        │
              │   OCRParser.parse(spans, barcodes) ─ pure & deterministic ─┐    │
              │     · label-aware  · confusion-normalize IDs  · validate    │    │
              │     · combine(recognition_conf × pattern_strength)          │    │
              │     · highest-confidence candidate wins per FieldType       │    │
              │                                          ↓                        │
              │   OCRExtraction: fields[], spans[], barcodes[], identity,        │
              │     engine_name/version, created_at, source_hashes              │
              └──────────────────────────────────────────────────────────────────┘

POST /ocr/parse ─▶ OCRService.parse(spans, barcodes) ─ parser only (no image)
GET  /ocr/fields ─▶ FieldType.values()
```

Layering is unchanged (`api → ocr/service → ocr/{backends,barcode,parser} →
preprocessing → utils/configs`). The backends are `ocr/` adapters; the
normalization domain lives in `ocr/` (models, patterns, parser, service).

## Domain models

`ocr/models.py` — frozen, slotted dataclasses (no HTTP, no I/O), so every stage
is independently testable and the whole engine is deterministic. The pipeline
flows `TextSpan`/`BarcodeResult` → `ExtractedField` → `OCRExtraction`, with
`OCRIdentity` as the small fingerprint-facing projection.

```python
class FieldType(str, Enum):        # declaration-ordered
    MANUFACTURER = "manufacturer"
    MODEL = "model"
    SERIAL_NUMBER = "serial_number"
    IMEI = "imei"
    MAC_ADDRESS = "mac_address"
    QR_CODE = "qr_code"
    BARCODE = "barcode"

class FieldSource(str, Enum):      # where a value came from
    TEXT = "text"; BARCODE = "barcode"; QR = "qr"

@dataclass(frozen=True, slots=True)
class TextSpan:                    # one raw OCR detection
    text: str; confidence: float
    bounding_box: tuple[int, int, int, int] | None = None

@dataclass(frozen=True, slots=True)
class BarcodeResult:               # one decoded QR/barcode
    kind: str; payload: str; symbology: str = ""; confidence: float = 1.0

@dataclass(frozen=True, slots=True)
class ExtractedField:              # a normalized, scored identity field
    field_type: FieldType; value: str; confidence: float
    raw_text: str = ""; source: FieldSource = FieldSource.TEXT

@dataclass(frozen=True, slots=True)
class OCRExtraction:               # the full result + provenance
    fields: tuple[ExtractedField, ...] = ()
    spans: tuple[TextSpan, ...] = ()
    barcodes: tuple[BarcodeResult, ...] = ()
    engine_name: str = "ocr"; engine_version: str = ""
    created_at: datetime | None = None
    source_hashes: tuple[str, ...] = ()
    def get(self, field_type) -> ExtractedField | None: ...
    def value_of(self, field_type) -> str: ...
    @property
    def identity(self) -> OCRIdentity: ...
    def to_dict(self) -> dict[str, object]: ...
    @classmethod
    def from_dict(cls, data) -> OCRExtraction: ...

@dataclass(frozen=True, slots=True)
class OCRIdentity:                 # fingerprint-facing projection
    manufacturer: str = ""; model: str = ""; serial_number: str = ""
    imei: str = ""; mac_address: str = ""
    @property
    def is_empty(self) -> bool: ...
    def non_empty(self) -> dict[str, str]: ...   # only populated fields
```

`OCRExtraction.to_dict` always includes the `identity` key (all five sub-keys
present, empty string when absent). `OCRIdentity.non_empty()` — the projection
the fingerprint engine consumes — drops blank fields so an absent field is never
attached downstream.

## Patterns & normalization

`ocr/patterns.py` — **pure, dependency-free** matchers (regex + small
validators). Each returns a `PatternCandidate(value, strength, raw_text)` whose
**pattern strength** ∈ `[0, 1]` reflects how strongly the text matches the
expected shape. Everything is deterministic and side-effect free, so the whole
extraction layer is unit-testable from hand-built strings.

| Field | Matcher | Rule | Strength |
|---|---|---|---|
| **IMEI** | `find_imei` | 15 digits (confusion-normalized first), validated by **Luhn** | `0.98` Luhn-pass · `0.55` shape-only |
| **MAC** | `find_mac` | `([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}`, upper-cased & colon-joined | `0.97` |
| **Serial** | `find_serial` | mixed alnum token, len 6–26; unlabelled must be digit+letter | `0.9` labelled+mixed · `0.7` either |
| **Model** | `find_model` | **label-required** (no intrinsic shape); whitespace-collapsed | `0.85` |
| **Manufacturer** | `find_manufacturer` | case-insensitive **keyword table**, exact-token boundary | `0.95` |

**OCR-confusion normalization** (`normalize_confusions`: `O`→`0`, `o`→`0`,
`I`→`1`, `l`→`1`, `S`→`5`, `B`→`8`) is applied **only** to structured-ID
candidates (IMEI/MAC digit runs) *before* validation — **never** to free text
like a manufacturer name, where `O`→`0` would corrupt the value. Serials are
deliberately **not** confusion-normalized (they legitimately contain letters).

**Label detection** — `has_serial_label` / `has_model_label` / `has_imei_label`
/ `has_mac_label` recognize prefixes like `S/N`, `Model`, `IMEI`, `MAC`;
`strip_label` isolates the value after the first `:` or `=`. A label both raises
a field's pattern strength and isolates its value before matching.

The manufacturer keyword table (`known_manufacturers()`) currently covers Dell,
HP, Apple, Samsung, Lenovo, Asus, Acer, Microsoft, Sony, LG, Toshiba, Google,
Xiaomi, Huawei, Nokia, Motorola, OnePlus — new brands are added in one place.

## Parser

`ocr/parser.py` — `OCRParser.parse(spans, barcodes=None) -> OCRExtraction`, the
normalization layer at the heart of the engine. It is **pure and deterministic**:
no image, no backend, no clock, so it is fully unit-testable from hand-built
inputs — which is exactly what `POST /ocr/parse` exposes.

**Per-field confidence:**

```
field_confidence = clamp(recognition_conf × pattern_strength × label_boost, 0, 1)
```

- `recognition_conf` — the backend's confidence in the span (`1.0` for a clean
  barcode payload).
- `pattern_strength` — how strongly the text matches the expected shape (a
  Luhn-valid IMEI outscores a bare digit run).
- `label_boost` — a small (`1.05`) multiplier when an IMEI label is present;
  the clamp guarantees the result never exceeds `1.0`.

**Label awareness** — a span like `"S/N: ABC123"` both *labels* the value
(raising its serial pattern strength) and *isolates* it (the label is stripped
before matching). **Barcode mining** — QR/barcode payloads become
`QR_CODE`/`BARCODE` fields **and** are additionally mined for an embedded IMEI
(preferred) or serial, since device labels frequently encode the serial in the
barcode. **Selection** — every candidate per field type is collected and the
**highest-confidence** one wins, tie-broken by value for determinism.

## Text backends

`ocr/backends.py` — the `OCRBackend` ABC plus two implementations, following the
optional-dependency adapter pattern established by the M1.4 detector and M1.5
CLIP encoder:

```python
class OCRBackend(ABC):
    name: str = "ocr"
    version: str = "mock-1.0.0"
    @property
    def is_ready(self) -> bool: ...              # mocks always ready
    @abstractmethod
    def recognize(self, image: LoadedImage) -> list[TextSpan]: ...
    def recognize_batch(self, images) -> list[TextSpan]: ...   # concat, image order
```

- **`EasyOCRBackend`** — a real, pretrained EasyOCR reader behind an import
  guard. `easyocr` is a heavy optional dependency (`requirements-models.txt`);
  its import and every backend-present code path are `# pragma: no cover`.
  Weights/model-storage are resolved from settings relative to `MODEL_DIR`
  (never a hardcoded path). Construction **never raises** — on any failure the
  backend is simply *not ready* and the caller falls back to the mock. The
  row→span mapping (`readtext` `(bbox, text, confidence)` rows → `TextSpan`, with
  `min_confidence` filtering and polygon→axis-aligned-box reduction) is
  **injectable** via `recognize_fn`, so it is unit-tested with a tiny fake — no
  torch/GPU. EasyOCR is *pretrained*: a serving-only plug-in with **no trainer**,
  exactly like the CLIP encoder.
- **`MockOCRBackend`** (`version="mock-ocr-m16-1.0.0"`) — deterministic synthetic
  spans derived from the batch content hash (same images → same spans), so the
  parser and service run end to end in the base environment without any weights.
  It emits **labelled** identity text (manufacturer/model/serial/IMEI/MAC) —
  including a **Luhn-completed** IMEI — to exercise the parser's label-aware
  paths. It is intentionally distinct from `predictor.MockOCREngine` (which
  serves the frozen `/predict` serial+model envelope).

## Barcode/QR reader

`ocr/barcode.py` — the `BarcodeReader` ABC plus two implementations, the same
adapter pattern:

```python
class BarcodeReader(ABC):
    name: str = "barcode"
    version: str = "mock-1.0.0"
    @property
    def is_ready(self) -> bool: ...
    @abstractmethod
    def decode(self, image: LoadedImage) -> list[BarcodeResult]: ...
    def decode_batch(self, images) -> list[BarcodeResult]: ...
```

- **`OpenCVBarcodeReader`** — real QR decoding via `cv2.QRCodeDetector` and 1-D
  barcodes via `cv2.barcode.BarcodeDetector`, behind an import guard.
  `opencv-python-headless` is optional; the import and decode paths are
  `# pragma: no cover`. Construction never raises → not-ready on failure. The
  decode step is **injectable** (`decode_fn`) for testing.
- **`MockBarcodeReader`** (`version="mock-barcode-1.0.0"`) — deterministic: one
  QR (`SN<hash8>`, symbology `QRCODE`) and one 1-D barcode (12 hash-derived
  digits, symbology `EAN13`) per image, so the parser's barcode-mining path is
  exercised in the base environment.

## Service orchestration

`ocr/service.py` — `OCRService`, the single collaborator the API layer depends
on. All collaborators (backend, barcode reader, parser, clock) are injected.

```python
class OCRService:
    def __init__(self, *, backend: OCRBackend, parser: OCRParser,
                 barcode_reader: BarcodeReader | None = None,
                 clock: Callable[[], datetime] = _utc_now) -> None: ...

    def extract(self, images: list[LoadedImage]) -> OCRExtraction: ...
    def parse(self, spans, barcodes=None) -> OCRExtraction: ...
    def identity_for(self, images) -> OCRIdentity: ...
```

- `extract()` — recognize text across the batch, decode barcodes/QR (when a
  reader is configured), run the parser **once** over the union, then stamp
  provenance: the backend identity, the `created_at` (injected clock) and the
  **sorted** source-image content hashes (reusing `img.sha256`).
- `parse()` — run the parser over client-supplied spans/barcodes (no images);
  provenance is stamped without source hashes. Powers `POST /ocr/parse`.
- `identity_for()` — the `OCRIdentity` projection convenience for the optional
  fingerprint seam (the fingerprint service can be handed this identity without
  importing the OCR engine).

## API surface

`api/ocr_routes.py` — three endpoints under `/ocr` (mounted alongside the
existing prediction/dataset/fingerprint routers in `application.py`). Routes are
thin: validate/convert input, delegate to the injected `OCRService`, serialise.

### `POST /ocr/extract`

`multipart/form-data`. Field **`images`**: 1–`MAX_IMAGES` files (same validation
as `/predict` and `/fingerprint/generate` via `validator.validate_batch`).

**Returns:** `OCRResponse` (fields[], spans[], barcodes[], identity, engine_name,
engine_version, created_at, source_hashes).

### `POST /ocr/parse`

`application/json`: `{ "spans": [...], "barcodes": [...] }` mirroring `TextSpan`
/ `BarcodeResult`. Runs the **parser only**, so the normalization layer is
demonstrable/testable without images. Confidence values are validated to `[0,1]`
by Pydantic (out-of-range → `422`).

**Returns:** `OCRResponse` (no source hashes).

### `GET /ocr/fields`

**Returns:** `FieldTypesResponse` — `{ "field_types": [...] }` enumerating every
supported `FieldType` value, in declaration order (discovery).

### OCR error envelope codes

Registered in `exceptions.py`; same envelope shape as the prediction errors:

| Code | HTTP | Meaning |
|---|---|---|
| `OCR_ERROR` | 500 | Base OCR engine failure |
| `OCR_BACKEND_NOT_READY` | 503 | The OCR recognition backend has no reader loaded |
| `OCR_PARSE_ERROR` | 422 | Malformed spans/barcodes submitted to the parser |

Validation failures on `/ocr/extract` reuse the shared image-validation codes
(`NO_IMAGES_PROVIDED` 400, `TOO_MANY_IMAGES` 400, `FILE_TOO_LARGE` 413,
`UNSUPPORTED_MEDIA_TYPE` 415, `CORRUPTED_IMAGE` 422, `INVALID_IMAGE_DIMENSIONS`
422).

## Guarded production swap

`api/dependencies.py` chooses each backend at process start (cached singletons),
mirroring `get_fingerprint_encoder`:

```
# text backend
if settings.ocr_backend == "easyocr":
    backend = _build_easyocr_backend(settings)   # never raises
    if backend is not None and backend.is_ready:  # easyocr + artifact + load ok
        return backend                            # real EasyOCR
return MockOCRBackend()                            # honest fallback

# barcode reader
reader = OpenCVBarcodeReader()                     # never raises
return reader if reader.is_ready else MockBarcodeReader()
```

`get_ocr_service(settings=Depends(get_settings))` builds a per-request
`OCRService` from the cached backend/reader singletons; the barcode reader is
attached only when `barcode_enabled` is set. `reset_dependency_caches()` clears
the `get_ocr_backend`/`get_barcode_reader` `@lru_cache`s alongside the existing
ones. Both real and mock backends return the identical `TextSpan`/`BarcodeResult`
shapes, so the swap is invisible to the parser/service — and CI / the base
environment (no easyocr/cv2) stay green on the mock path.

## Configuration

Additive, backwards-compatible env vars (defaults keep the mock path green):

| Variable | Default | Description |
|---|---|---|
| `OCR_BACKEND` | `easyocr` | Recognition backend: `easyocr` (auto-degrades to mock when unavailable) or `mock`. |
| `OCR_LANGUAGES` | `["en"]` | Language codes passed to the EasyOCR reader. |
| `OCR_WEIGHTS` | `ocr` | Model-storage locator under `MODEL_DIR` (or absolute). Absent/unloadable → mock fallback. |
| `OCR_USE_GPU` | `false` | Whether to request GPU inference from the EasyOCR reader. |
| `OCR_MIN_CONFIDENCE` | `0.30` | Recognition confidence below which EasyOCR rows are discarded before parsing. |
| `BARCODE_ENABLED` | `true` | Whether the engine decodes QR/barcodes alongside text; when false, no reader is attached. |

## Optional fingerprint-identity seam

The M1.5 fingerprint engine can **optionally** consume an `OCRIdentity` without
breaking backward compatibility:

- `DeviceFingerprint` gained an optional `identity: dict[str, str] = field(
  default_factory=dict)`. `to_dict()` emits the `identity` key **only when
  non-empty**, and `from_dict` reads it via `.get("identity", {})` — so M1.5
  byte-stable example artifacts and all existing tests stay identical.
- `FingerprintService.generate(...)` gained an optional keyword
  `identity: OCRIdentity | None = None`; when supplied, its **non-empty** fields
  are attached (`identity.non_empty()`). Default `None` → behaviour
  byte-identical to M1.5.
- `FingerprintResponse` gained an optional `identity` field (empty dict by
  default).
- **No cross-engine hard dependency**: the fingerprint core imports `OCRIdentity`
  only under `TYPE_CHECKING`; the identity is *passed in*, never imported at
  runtime, so the two engines stay decoupled.

## Testing

All M1.6 tests run in the **base environment** (no easyocr/cv2/torch) via
injected fakes. From `intelligence/device_ai`:

```bash
pytest tests/test_ocr_patterns.py \
       tests/test_ocr_models.py \
       tests/test_ocr_parser.py \
       tests/test_ocr_backends.py \
       tests/test_ocr_barcode.py \
       tests/test_ocr_service.py \
       tests/test_ocr_routes.py \
       tests/test_fingerprint_identity.py -q
```

- `test_ocr_patterns.py` — IMEI Luhn accept/reject, MAC match/normalization,
  confusion normalization only on IDs, manufacturer keyword table (`"Delaware"`
  is not a false positive), serial heuristic, label helpers, `strip_label`.
- `test_ocr_models.py` — `FieldType` order, `to_dict`/accessors, `OCRIdentity`
  emptiness/projection, `OCRExtraction` `to_dict`/`from_dict` round-trip.
- `test_ocr_parser.py` — label-aware extraction, per-field confidence combination
  and clamp, best-selection, barcode/QR → fields, embedded IMEI/serial mining,
  empty input, and the shared `sample_spans` fixture.
- `test_ocr_backends.py` — `MockOCRBackend` determinism + Luhn-valid IMEI;
  `EasyOCRBackend` not-ready without the backend; injected `recognize_fn` maps
  rows → spans (bbox, `min_confidence` filter, flat-row-list shape).
- `test_ocr_barcode.py` — `MockBarcodeReader` determinism (QR + barcode);
  `OpenCVBarcodeReader` not-ready without cv2; injected `decode_fn`.
- `test_ocr_service.py` — `extract` stamps engine identity/time/sorted source
  hashes/full identity, barcode-presence toggle, determinism; `parse`
  (spans-only + barcodes); `identity_for`.
- `test_ocr_routes.py` — `/ocr/extract` happy + validation reuse, `/ocr/parse`
  happy + out-of-range `422`, `/ocr/fields`; **`/predict` contract unchanged**
  and `/fingerprint/generate` identity backward-compat assertions.
- `test_fingerprint_identity.py` — `generate` with/without identity; `to_dict`
  omits `identity` when empty (guards M1.5 byte-stability); round-trip.

## Integration guide

To serve **real** OCR (replace the mocks):

1. Install the optional model dependencies:

   ```bash
   cd intelligence/device_ai
   source .venv/bin/activate                 # Windows: .venv\Scripts\activate
   pip install -r requirements-models.txt    # easyocr, opencv-python-headless
   ```

2. Provide EasyOCR weights under `MODEL_DIR` (default `models/`) in a
   subdirectory named `ocr/` (or any name resolvable via `OCR_WEIGHTS`). EasyOCR
   is pretrained — download its language models (offline: pre-place them so the
   reader constructs with `download_enabled=False`).

   ```
   models/
   └── ocr/
       └── <easyocr language model artifacts>
   ```

3. Set environment variables (all optional; defaults already select EasyOCR):

   ```bash
   export OCR_BACKEND=easyocr
   export OCR_LANGUAGES='["en"]'
   export OCR_WEIGHTS=ocr                     # points to models/ocr/
   export OCR_MIN_CONFIDENCE=0.30
   export BARCODE_ENABLED=true                # OpenCV QR/barcode decoding
   ```

4. Restart the service. `get_ocr_backend()` / `get_barcode_reader()` load the
   real backends on next start; `/ocr/*` now use genuine OCR.

**No code changes required** — the backends are swapped via dependency
injection. OpenCV barcode/QR decoding activates automatically whenever
`opencv-python-headless` is importable and `BARCODE_ENABLED` is true.

## Example requests & responses

### Extract identity from images

```bash
curl -X POST http://localhost:8100/ocr/extract \
  -F "images=@device_label.jpg"
```

**Response `200`** (fields truncated for brevity)

```json
{
  "fields": [
    { "field_type": "manufacturer", "value": "Dell", "confidence": 0.9215,
      "raw_text": "Dell", "source": "text" },
    { "field_type": "imei", "value": "019510777635357", "confidence": 0.90552,
      "raw_text": "IMEI: 019510777635357", "source": "text" },
    { "field_type": "qr_code", "value": "SN0FE1B9C5", "confidence": 0.99,
      "raw_text": "SN0FE1B9C5", "source": "qr" }
  ],
  "spans": [ { "text": "Dell", "confidence": 0.97, "bounding_box": null } ],
  "barcodes": [
    { "kind": "qr", "payload": "SN0FE1B9C5", "symbology": "QRCODE", "confidence": 0.99 }
  ],
  "identity": {
    "manufacturer": "Dell", "model": "XPS-0FE1",
    "serial_number": "SN0FE1B9C5", "imei": "019510777635357",
    "mac_address": "0F:E1:B9:C5:F1:CD"
  },
  "engine_name": "ocr",
  "engine_version": "mock-ocr-m16-1.0.0",
  "created_at": "2026-08-01T12:00:00+00:00",
  "source_hashes": ["0fe1b9c5f1cd0de77f76c3535ed0225c85cb059892568f5db7f142a92fdaf12b"]
}
```

### Parse client-supplied spans (no image)

```bash
curl -X POST http://localhost:8100/ocr/parse \
  -H 'Content-Type: application/json' \
  -d '{
    "spans": [
      {"text": "Dell Inc.", "confidence": 0.98},
      {"text": "S/N: ABC12345", "confidence": 0.93}
    ],
    "barcodes": [{"kind": "qr", "payload": "490154203237518"}]
  }'
```

**Response `200`** — the parser normalizes the spans (manufacturer `Dell`,
serial `ABC12345`) and mines the QR payload for a **Luhn-valid IMEI**
(`490154203237518`).

### Discover supported fields

```bash
curl http://localhost:8100/ocr/fields
```

```json
{ "field_types": ["manufacturer", "model", "serial_number", "imei",
                  "mac_address", "qr_code", "barcode"] }
```

Illustrative, byte-stable OCR artifacts (a full extract response, the parse
examples and a field-level evaluation report) are checked in under
[`docs/examples/ocr/`](../examples/ocr/) (regenerate with
`python -m device_ai.scripts.gen_ocr_examples`).

## Backward compatibility

The existing `/predict` contract is **completely unchanged** — its
`ocr: {serial_number, model}` object is still produced by the untouched
`predictor.MockOCREngine`, and `/predict` is unaware of the M1.6 engine. The new
`/ocr/*` endpoints are an **additive** surface under a separate prefix.

The fingerprint-identity seam is **byte-stable**: a fingerprint generated
without an `OCRIdentity` serializes exactly as it did in M1.5 (the `identity`
key is omitted when empty), so the M1.5 example artifacts and all existing
fingerprint tests remain identical.

## Design rationale

**Why a separate `ocr/` subsystem instead of extending `predictor.OCREngine`?**
The `/predict` `OCREngine` is bound to a frozen two-field (serial + model)
envelope. M1.6 extracts seven confidence-scored fields plus raw spans/barcodes
and a normalization layer — overloading `/predict` would break its byte-stable
contract. Mirroring M1.5's `fingerprint/` package keeps the rich engine additive
and the frozen contract untouched.

**Why a pure, image-free parser?** Separating *recognition* (backends) from
*normalization* (parser) means the entire label-awareness, confusion-handling,
validation and confidence-scoring logic is deterministic and unit-testable from
hand-built strings — and directly exposable as `POST /ocr/parse`. It also lets a
real EasyOCR read and a mock read flow through the identical scoring path.

**Why confusion-normalize only structured IDs?** `O`→`0` is the right call for a
15-digit IMEI but corrupts a manufacturer name or an alphanumeric serial.
Applying the mapping *per candidate* (IDs only, before validation) captures the
benefit without the collateral damage.

**Why pass identity into the fingerprint engine instead of importing OCR?**
Importing the OCR engine into the fingerprint core would couple two independent
subsystems and pull OCR's optional dependencies into the fingerprint path. A
plain `OCRIdentity` value passed in (typed under `TYPE_CHECKING` only) keeps the
engines decoupled and the seam backward-compatible.

**Why dependency-inject the backends/reader/clock?** The heavy backends
(easyocr/opencv) are absent in CI and the base environment. Injecting a
`recognize_fn`/`decode_fn` (or the mock) and the clock lets every unit of
parsing/scoring/mapping logic be tested deterministically with tiny fakes, while
the real backend paths are marked `# pragma: no cover`.

---

_Part of **EcoTrace India** — IEEE YESIST 2026. See the module
[`README.md`](../../README.md), [`training/README.md`](../../training/README.md)
and the platform-wide `docs/engineering/` standards._
