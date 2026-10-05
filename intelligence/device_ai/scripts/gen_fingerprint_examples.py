"""Generate illustrative fingerprint artifacts for docs/examples/fingerprint.

Renders example fingerprint responses (generate + compare) and a **similarity
evaluation report** (JSON + Markdown) from the deterministic
:class:`MockEmbeddingEncoder` with an injected fixed clock and *sequential*
EcoIDs, so the output is **byte-stable**. No real CLIP model is trained,
downloaded or executed here (the base environment has neither open-clip-torch
nor torch); the embeddings are the deterministic mock's, standing in for a real
OpenCLIP encoder.

The similarity report evaluates every metric (cosine/euclidean/manhattan) over a
small fixed set of synthetic device images, showing intra-device (same image →
similarity 1.0) and inter-device separation — the raw material a threshold is
chosen from.

Usage (from ``intelligence/`` with ``PYTHONPATH=.``)::

    python -m device_ai.scripts.gen_fingerprint_examples
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from PIL import Image

from device_ai.fingerprint.repository import InMemoryFingerprintRepository
from device_ai.fingerprint.service import FingerprintService
from device_ai.fingerprint.similarity import SimilarityMetric, compute_similarity
from device_ai.fingerprint.verification import VerificationEngine
from device_ai.inference.ecoid import EcoIDGenerator
from device_ai.inference.predictor import MockEmbeddingEncoder
from device_ai.preprocessing.image_loader import LoadedImage, load_image

_FIXED_CLOCK = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
_EXAMPLES_DIR = (
    Path(__file__).resolve().parents[1] / "docs" / "examples" / "fingerprint"
)
_THRESHOLD = 0.85
_METRIC = "cosine"

#: Synthetic device catalogue: a stable name → solid RGB fill. Distinct colours
#: yield distinct deterministic mock embeddings.
_DEVICES: dict[str, tuple[int, int, int]] = {
    "laptop_dell": (10, 20, 30),
    "phone_apple": (200, 100, 50),
    "tablet_samsung": (60, 180, 120),
}


def _load(color: tuple[int, int, int]) -> LoadedImage:
    """Return a decoded LoadedImage of a solid colour for the examples."""
    buffer = BytesIO()
    Image.new("RGB", (256, 256), color).save(buffer, format="PNG")
    return load_image(
        buffer.getvalue(), filename="device.png", content_type="image/png"
    )


def _make_service(
    repository: InMemoryFingerprintRepository,
) -> FingerprintService:
    """Build a deterministic service (mock encoder, fixed clock, sequential IDs).

    Sequential EcoIDs make the generated example files byte-stable across runs
    (the default UUID-backed IDs would differ every run).
    """
    generator = EcoIDGenerator(year=2026)
    # Patch generate() to the sequential variant for reproducible example IDs.
    generator.generate = generator.generate_sequential  # type: ignore[method-assign]
    return FingerprintService(
        encoder=MockEmbeddingEncoder(),
        repository=repository,
        ecoid_generator=generator,
        verifier=VerificationEngine(threshold=_THRESHOLD, metric=_METRIC),
        clock=lambda: _FIXED_CLOCK,
    )


def _write_json(path: Path, payload: object) -> None:
    """Write ``payload`` as pretty, sorted, newline-terminated JSON."""
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _build_similarity_report(
    fingerprints: dict[str, list[float]],
) -> dict[str, object]:
    """Return a similarity-evaluation document across every metric.

    Args:
        fingerprints: Mapping of device name → its normalized embedding.

    Returns:
        A JSON-serialisable report with, per metric, the full pairwise
        similarity matrix and the intra/inter-device similarity summary.
    """
    names = sorted(fingerprints)
    metrics_report: dict[str, object] = {}
    for metric in SimilarityMetric:
        matrix: dict[str, dict[str, float]] = {}
        inter_scores: list[float] = []
        for left in names:
            row: dict[str, float] = {}
            for right in names:
                score = compute_similarity(
                    fingerprints[left], fingerprints[right], metric
                )
                row[right] = round(score.similarity, 6)
                if left < right:
                    inter_scores.append(score.similarity)
            matrix[left] = row
        metrics_report[metric.value] = {
            "similarity_matrix": matrix,
            "intra_device_similarity": 1.0,  # same embedding → 1.0 by construction
            "max_inter_device_similarity": round(max(inter_scores), 6),
            "min_inter_device_similarity": round(min(inter_scores), 6),
        }
    return {
        "generated_at": _FIXED_CLOCK.isoformat(),
        "encoder_name": "clip",
        "encoder_version": MockEmbeddingEncoder.version,
        "dimension": MockEmbeddingEncoder.dimension,
        "match_threshold": _THRESHOLD,
        "default_metric": _METRIC,
        "devices": names,
        "metrics": metrics_report,
    }


def _report_to_markdown(report: dict[str, object]) -> str:
    """Render the similarity report as a human-readable Markdown document."""
    lines: list[str] = []
    lines.append("# Fingerprint Similarity Evaluation Report")
    lines.append("")
    lines.append(
        "> Illustrative, byte-stable report generated from the deterministic "
        "`MockEmbeddingEncoder` (no real CLIP model executed). Regenerate with "
        "`python -m device_ai.scripts.gen_fingerprint_examples`."
    )
    lines.append("")
    lines.append(f"- **Generated at:** {report['generated_at']}")
    lines.append(
        f"- **Encoder:** {report['encoder_name']} "
        f"({report['encoder_version']}), dimension {report['dimension']}"
    )
    lines.append(f"- **Default metric:** {report['default_metric']}")
    lines.append(f"- **Match threshold:** {report['match_threshold']}")
    lines.append(f"- **Devices:** {', '.join(report['devices'])}")  # type: ignore[arg-type]
    lines.append("")

    metrics = report["metrics"]
    assert isinstance(metrics, dict)
    names = report["devices"]
    assert isinstance(names, list)
    for metric_name, data in metrics.items():
        assert isinstance(data, dict)
        lines.append(f"## Metric: `{metric_name}`")
        lines.append("")
        lines.append(
            f"- Intra-device similarity (same image): "
            f"**{data['intra_device_similarity']}**"
        )
        lines.append(
            f"- Max inter-device similarity: "
            f"**{data['max_inter_device_similarity']}**"
        )
        lines.append(
            f"- Min inter-device similarity: "
            f"**{data['min_inter_device_similarity']}**"
        )
        lines.append("")
        header = "| device | " + " | ".join(names) + " |"
        separator = "|---|" + "---|" * len(names)
        lines.append(header)
        lines.append(separator)
        matrix = data["similarity_matrix"]
        assert isinstance(matrix, dict)
        for left in names:
            row = matrix[left]
            cells = " | ".join(f"{row[right]:.4f}" for right in names)
            lines.append(f"| **{left}** | {cells} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    """Generate the example fingerprint artifacts."""
    _EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    repository = InMemoryFingerprintRepository()
    service = _make_service(repository)

    # Generate a fingerprint per device and keep their embeddings for the report.
    fingerprints: dict[str, list[float]] = {}
    generated_responses: dict[str, dict[str, object]] = {}
    device_meta = {
        "laptop_dell": ("Laptop", "Dell"),
        "phone_apple": ("Smartphone", "Apple"),
        "tablet_samsung": ("Tablet", "Samsung"),
    }
    for name, color in _DEVICES.items():
        device_type, brand = device_meta[name]
        fingerprint = service.generate(
            [_load(color)], device_type=device_type, brand=brand
        )
        fingerprints[name] = list(fingerprint.embedding)
        # to_dict already produces an API-shaped, JSON-friendly payload.
        payload = fingerprint.to_dict()
        payload["created_at"] = fingerprint.created_at.isoformat()
        generated_responses[name] = payload

    # Write a single representative generate response (the first device).
    _write_json(
        _EXAMPLES_DIR / "generate_response.json",
        generated_responses["laptop_dell"],
    )

    # Compare two distinct devices and one identical pair.
    left_id = generated_responses["laptop_dell"]["eco_id"]
    right_id = generated_responses["phone_apple"]["eco_id"]
    assert isinstance(left_id, str)
    assert isinstance(right_id, str)
    result = service.compare(left_id, right_id)
    _write_json(
        _EXAMPLES_DIR / "compare_response.json",
        {
            "left_eco_id": result.left_eco_id,
            "right_eco_id": result.right_eco_id,
            "metric": result.metric.value,
            "similarity": round(result.similarity, 6),
            "distance": round(result.distance, 6),
            "threshold": result.threshold,
            "decision": result.decision.value,
            "is_match": result.is_match,
        },
    )

    # Similarity evaluation report (JSON + Markdown) across every metric.
    report = _build_similarity_report(fingerprints)
    _write_json(_EXAMPLES_DIR / "similarity_report.json", report)
    (_EXAMPLES_DIR / "similarity_report.md").write_text(
        _report_to_markdown(report), encoding="utf-8"
    )

    print(f"Wrote example fingerprint artifacts to {_EXAMPLES_DIR}")


if __name__ == "__main__":
    main()
