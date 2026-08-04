"""Tests for the model exporters (milestone M1.3).

torch and onnx are not installed in the base test environment, so every export
must return a ``skipped`` outcome rather than raise or silently succeed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from device_ai.exceptions import UnsupportedExportFormatError
from device_ai.training.core.exporter import (
    SUPPORTED_EXPORT_FORMATS,
    ExportPlan,
    ExportRecord,
    OnnxExporter,
    PyTorchExporter,
    SkippedExport,
    TorchScriptExporter,
    export_model,
    get_exporter,
)


def test_export_record_flags() -> None:
    exported = ExportRecord("onnx", "exported", location="a.onnx")
    skipped = SkippedExport("onnx", "no torch")
    assert exported.exported is True
    assert exported.skipped is False
    assert skipped.skipped is True
    assert skipped.exported is False
    assert skipped.export_format == "onnx"


@pytest.mark.parametrize(
    "exporter",
    [PyTorchExporter(), TorchScriptExporter(), OnnxExporter()],
)
def test_exporters_skip_without_torch(exporter, tmp_path: Path) -> None:
    record = exporter.export(object(), tmp_path / "model.bin")
    assert record.skipped is True
    assert "not installed" in record.message
    # Nothing was written.
    assert not any(tmp_path.iterdir())


def test_get_exporter_known_formats() -> None:
    for fmt in SUPPORTED_EXPORT_FORMATS:
        assert get_exporter(fmt).export_format == fmt


def test_get_exporter_case_insensitive() -> None:
    assert get_exporter("PyTorch").export_format == "pytorch"


def test_get_exporter_unknown_raises() -> None:
    with pytest.raises(UnsupportedExportFormatError, match="Unsupported export"):
        get_exporter("tensorrt")


def test_export_model_returns_one_record_per_format(tmp_path: Path) -> None:
    plan = ExportPlan(model_name="m", version="1.0.0")
    records = export_model(model=None, plan=plan, exports_dir=tmp_path)
    assert [r.export_format for r in records] == list(SUPPORTED_EXPORT_FORMATS)
    assert all(r.skipped for r in records)


def test_export_model_custom_formats(tmp_path: Path) -> None:
    plan = ExportPlan(model_name="m", version="1.0.0", formats=("onnx",))
    records = export_model(model=None, plan=plan, exports_dir=tmp_path)
    assert len(records) == 1
    assert records[0].export_format == "onnx"


def test_export_plan_default_formats() -> None:
    plan = ExportPlan(model_name="m", version="1.0.0")
    assert plan.formats == SUPPORTED_EXPORT_FORMATS
