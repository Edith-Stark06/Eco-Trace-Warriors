"""Generate illustrative OCR artifacts for docs/examples/ocr.

Renders example OCR outputs (a full ``/ocr/extract`` response, several
``/ocr/parse`` normalization cases) and a **field-level evaluation report**
(JSON + Markdown) from the deterministic mock OCR backend and mock barcode
reader with an injected fixed clock, so the output is **byte-stable**. No real
EasyOCR/OpenCV model is downloaded or executed here (the base environment has
neither ``easyocr`` nor ``opencv-python-headless``); the spans/barcodes are the
mocks', standing in for a real OCR backend.

The evaluation report scores the parser over a small **labelled synthetic set**
of noisy spans (per-field correctness + a confidence summary), the raw material
a field-confidence threshold is chosen from.

Usage (from ``intelligence/`` with ``PYTHONPATH=.``)::

    python -m device_ai.scripts.gen_ocr_examples
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from PIL import Image

from device_ai.ocr.backends import MockOCRBackend
from device_ai.ocr.barcode import MockBarcodeReader
from device_ai.ocr.models import BarcodeResult, FieldType, TextSpan
from device_ai.ocr.parser import OCRParser
from device_ai.ocr.service import OCRService
from device_ai.preprocessing.image_loader import LoadedImage, load_image

_FIXED_CLOCK = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
_EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "docs" / "examples" / "ocr"

#: A fixed synthetic device image (solid fill) for the extract example. The mock
#: backend derives deterministic spans from its content hash.
_DEVICE_COLOR = (10, 20, 30)

#: Labelled synthetic parse cases: a human-readable name → the noisy spans a
#: backend might emit → the fields we expect the parser to recover. Drives both
#: the parse-examples artifact and the evaluation report.
_PARSE_CASES: tuple[dict[str, object], ...] = (
    {
        "name": "clean_label",
        "spans": [
            TextSpan(text="Dell Inc.", confidence=0.98),
            TextSpan(text="Model: XPS 15", confidence=0.95),
            TextSpan(text="S/N: ABC12345", confidence=0.93),
        ],
        "barcodes": [],
        "expected": {
            FieldType.MANUFACTURER: "Dell",
            FieldType.MODEL: "XPS 15",
            FieldType.SERIAL_NUMBER: "ABC12345",
        },
    },
    {
        "name": "imei_and_mac",
        "spans": [
            TextSpan(text="IMEI: 490154203237518", confidence=0.9),
            TextSpan(text="MAC 00-1A-2B-3C-4D-5E", confidence=0.88),
        ],
        "barcodes": [],
        "expected": {
            FieldType.IMEI: "490154203237518",
            FieldType.MAC_ADDRESS: "00:1A:2B:3C:4D:5E",
        },
    },
    {
        "name": "barcode_mined_serial",
        "spans": [TextSpan(text="Lenovo", confidence=0.92)],
        "barcodes": [
            BarcodeResult(kind="qr", payload="SNXY98765", symbology="QRCODE"),
        ],
        "expected": {
            FieldType.MANUFACTURER: "Lenovo",
            FieldType.QR_CODE: "SNXY98765",
            FieldType.SERIAL_NUMBER: "SNXY98765",
        },
    },
    {
        "name": "barcode_mined_imei",
        "spans": [],
        "barcodes": [
            BarcodeResult(
                kind="barcode", payload="490154203237518", symbology="CODE128"
            ),
        ],
        "expected": {
            FieldType.BARCODE: "490154203237518",
            FieldType.IMEI: "490154203237518",
        },
    },
)


def _load(color: tuple[int, int, int]) -> LoadedImage:
    """Return a decoded LoadedImage of a solid colour for the examples."""
    buffer = BytesIO()
    Image.new("RGB", (256, 256), color).save(buffer, format="PNG")
    return load_image(
        buffer.getvalue(), filename="device.png", content_type="image/png"
    )


def _make_service() -> OCRService:
    """Build a deterministic service (mock backend + reader, fixed clock)."""
    return OCRService(
        backend=MockOCRBackend(),
        parser=OCRParser(),
        barcode_reader=MockBarcodeReader(),
        clock=lambda: _FIXED_CLOCK,
    )


def _write_json(path: Path, payload: object) -> None:
    """Write ``payload`` as pretty, sorted, newline-terminated JSON."""
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _build_parse_examples() -> list[dict[str, object]]:
    """Return the parse cases with their spans, barcodes and parsed output."""
    parser = OCRParser()
    examples: list[dict[str, object]] = []
    for case in _PARSE_CASES:
        spans = list(case["spans"])  # type: ignore[arg-type]
        barcodes = list(case["barcodes"])  # type: ignore[arg-type]
        extraction = parser.parse(spans, barcodes)
        examples.append(
            {
                "name": case["name"],
                "input": {
                    "spans": [span.to_dict() for span in spans],
                    "barcodes": [barcode.to_dict() for barcode in barcodes],
                },
                "output": extraction.to_dict(),
            }
        )
    return examples


def _build_evaluation_report() -> dict[str, object]:
    """Score the parser over the labelled synthetic set (per-field accuracy)."""
    parser = OCRParser()
    per_field_total: dict[str, int] = {}
    per_field_correct: dict[str, int] = {}
    confidences: list[float] = []
    case_results: list[dict[str, object]] = []

    for case in _PARSE_CASES:
        spans = list(case["spans"])  # type: ignore[arg-type]
        barcodes = list(case["barcodes"])  # type: ignore[arg-type]
        expected = case["expected"]
        assert isinstance(expected, dict)
        extraction = parser.parse(spans, barcodes)

        fields_report: dict[str, dict[str, object]] = {}
        for field_type, want in expected.items():
            key = field_type.value
            got = extraction.value_of(field_type)
            correct = got == want
            per_field_total[key] = per_field_total.get(key, 0) + 1
            per_field_correct[key] = per_field_correct.get(key, 0) + int(correct)
            extracted = extraction.get(field_type)
            confidence = round(extracted.confidence, 6) if extracted else 0.0
            if extracted is not None:
                confidences.append(extracted.confidence)
            fields_report[key] = {
                "expected": want,
                "extracted": got,
                "correct": correct,
                "confidence": confidence,
            }
        case_results.append({"name": case["name"], "fields": fields_report})

    total = sum(per_field_total.values())
    correct = sum(per_field_correct.values())
    per_field_accuracy = {
        key: round(per_field_correct[key] / per_field_total[key], 6)
        for key in sorted(per_field_total)
    }
    return {
        "generated_at": _FIXED_CLOCK.isoformat(),
        "engine_name": MockOCRBackend.name,
        "engine_version": MockOCRBackend.version,
        "case_count": len(_PARSE_CASES),
        "field_count": total,
        "overall_accuracy": round(correct / total, 6) if total else 0.0,
        "mean_confidence": (
            round(sum(confidences) / len(confidences), 6) if confidences else 0.0
        ),
        "per_field_accuracy": per_field_accuracy,
        "cases": case_results,
    }


def _report_to_markdown(report: dict[str, object]) -> str:
    """Render the evaluation report as a human-readable Markdown document."""
    lines: list[str] = []
    lines.append("# OCR Parser Evaluation Report")
    lines.append("")
    lines.append(
        "> Illustrative, byte-stable report generated from the deterministic mock "
        "OCR backend and parser (no real EasyOCR/OpenCV executed). Regenerate with "
        "`python -m device_ai.scripts.gen_ocr_examples`."
    )
    lines.append("")
    lines.append(f"- **Generated at:** {report['generated_at']}")
    lines.append(f"- **Engine:** {report['engine_name']} ({report['engine_version']})")
    lines.append(f"- **Cases:** {report['case_count']}")
    lines.append(f"- **Fields evaluated:** {report['field_count']}")
    lines.append(f"- **Overall accuracy:** {report['overall_accuracy']}")
    lines.append(f"- **Mean field confidence:** {report['mean_confidence']}")
    lines.append("")

    lines.append("## Per-field accuracy")
    lines.append("")
    lines.append("| field | accuracy |")
    lines.append("|---|---|")
    per_field = report["per_field_accuracy"]
    assert isinstance(per_field, dict)
    for key, accuracy in per_field.items():
        lines.append(f"| `{key}` | {accuracy:.4f} |")
    lines.append("")

    lines.append("## Cases")
    lines.append("")
    cases = report["cases"]
    assert isinstance(cases, list)
    for case in cases:
        assert isinstance(case, dict)
        lines.append(f"### `{case['name']}`")
        lines.append("")
        lines.append("| field | expected | extracted | correct | confidence |")
        lines.append("|---|---|---|---|---|")
        fields = case["fields"]
        assert isinstance(fields, dict)
        for key, data in fields.items():
            assert isinstance(data, dict)
            mark = "✅" if data["correct"] else "❌"
            lines.append(
                f"| `{key}` | {data['expected']} | {data['extracted']} | "
                f"{mark} | {data['confidence']:.4f} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    """Generate the example OCR artifacts."""
    _EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    # Full /ocr/extract response over a single synthetic device image.
    service = _make_service()
    extraction = service.extract([_load(_DEVICE_COLOR)])
    _write_json(_EXAMPLES_DIR / "extract_response.json", extraction.to_dict())

    # Parsing examples: several noisy-input → parsed-field cases.
    _write_json(_EXAMPLES_DIR / "parse_examples.json", _build_parse_examples())

    # Field-level evaluation report (JSON + Markdown).
    report = _build_evaluation_report()
    _write_json(_EXAMPLES_DIR / "evaluation_report.json", report)
    (_EXAMPLES_DIR / "evaluation_report.md").write_text(
        _report_to_markdown(report), encoding="utf-8"
    )

    print(f"Wrote example OCR artifacts to {_EXAMPLES_DIR}")


if __name__ == "__main__":
    main()
