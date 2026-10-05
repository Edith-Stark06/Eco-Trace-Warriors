"""Model export adapters for the training platform (milestone M1.3).

Trained models are deployed in several formats — native PyTorch weights,
TorchScript and ONNX. Each format is handled by an adapter implementing the
:class:`ModelExporter` protocol. Because ``torch`` and ``onnx`` are optional,
uninstalled model dependencies (see ``requirements-models.txt``), every adapter
checks for its backend and, when absent, returns a :class:`ExportRecord` with
``status="skipped"`` instead of raising — so the platform is fully exercisable
in the base environment without silently pretending an export happened.

TensorRT export is explicitly **out of scope** for this milestone.

The torch-present code paths are minimal and marked ``# pragma: no cover``: no
model is trained in M1.3, so they never run in the test environment. The
import-guard and skip paths are covered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from loguru import logger

from ...exceptions import ExportError, UnsupportedExportFormatError

#: Export formats this module knows how to (attempt to) produce.
SUPPORTED_EXPORT_FORMATS: tuple[str, ...] = ("pytorch", "torchscript", "onnx")


@dataclass(frozen=True, slots=True)
class ExportRecord:
    """Outcome of a single export attempt.

    Attributes:
        export_format: The requested format (``"pytorch"``/``"torchscript"``/
            ``"onnx"``).
        status: ``"exported"`` when a file was written, ``"skipped"`` when the
            backend was unavailable, ``"failed"`` when the attempt errored.
        location: POSIX path of the produced file (empty when not written).
        message: Human-readable detail (reason for a skip/failure).
    """

    export_format: str
    status: str
    location: str = ""
    message: str = ""

    @property
    def exported(self) -> bool:
        """Whether an artifact file was actually written."""
        return self.status == "exported"

    @property
    def skipped(self) -> bool:
        """Whether the export was skipped (backend unavailable)."""
        return self.status == "skipped"


def SkippedExport(export_format: str, message: str) -> ExportRecord:  # noqa: N802
    """Construct a ``skipped`` :class:`ExportRecord` (readable call-site helper).

    Args:
        export_format: The format that was skipped.
        message: Why it was skipped (e.g. the missing backend).

    Returns:
        An :class:`ExportRecord` with ``status="skipped"``.
    """
    return ExportRecord(export_format=export_format, status="skipped", message=message)


def _torch_available() -> bool:
    """Return whether ``torch`` is importable in this environment."""
    try:  # pragma: no cover - torch is not installed in the base environment
        import torch  # noqa: F401
    except ImportError:
        return False
    return True  # pragma: no cover


def _onnx_available() -> bool:
    """Return whether ``onnx`` is importable in this environment."""
    try:  # pragma: no cover - onnx is not installed in the base environment
        import onnx  # noqa: F401
    except ImportError:  # pragma: no cover - reached only with torch-but-no-onnx
        return False
    return True  # pragma: no cover


@runtime_checkable
class ModelExporter(Protocol):
    """A backend that exports a model object to a single target format."""

    @property
    def export_format(self) -> str:
        """Return the format identifier this exporter produces."""
        ...

    def export(self, model: Any, destination: Path, **kwargs: Any) -> ExportRecord:
        """Export ``model`` to ``destination`` and return an outcome record."""
        ...


class PyTorchExporter:
    """Export a model's weights via ``torch.save`` (native ``.pt``)."""

    export_format = "pytorch"

    def export(self, model: Any, destination: Path, **kwargs: Any) -> ExportRecord:
        """Save the model's ``state_dict`` to ``destination``.

        Args:
            model: The model object to export (must expose ``state_dict()`` when
                torch is present).
            destination: Path the ``.pt`` file is written to.
            **kwargs: Ignored; accepted for a uniform exporter signature.

        Returns:
            An :class:`ExportRecord`; ``skipped`` when torch is unavailable.

        Raises:
            ExportError: If torch is present but saving fails.
        """
        if not _torch_available():
            return SkippedExport(
                self.export_format, "PyTorch is not installed; export skipped."
            )
        return self._export_with_torch(model, destination)  # pragma: no cover

    def _export_with_torch(  # pragma: no cover - requires optional torch
        self, model: Any, destination: Path
    ) -> ExportRecord:
        """Perform the real ``torch.save`` (only runs when torch is installed)."""
        import torch

        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            state = model.state_dict() if hasattr(model, "state_dict") else model
            torch.save(state, destination)
        except Exception as exc:  # noqa: BLE001 - re-raised as a domain error
            raise ExportError(
                f"PyTorch export failed: {exc}",
                details={"destination": str(destination)},
            ) from exc
        return ExportRecord(
            export_format=self.export_format,
            status="exported",
            location=destination.as_posix(),
        )


class TorchScriptExporter:
    """Export a model to TorchScript via ``torch.jit.script``."""

    export_format = "torchscript"

    def export(self, model: Any, destination: Path, **kwargs: Any) -> ExportRecord:
        """Script the model and save it to ``destination``.

        Args:
            model: The model object to script.
            destination: Path the ``.torchscript`` file is written to.
            **kwargs: Ignored; accepted for a uniform exporter signature.

        Returns:
            An :class:`ExportRecord`; ``skipped`` when torch is unavailable.

        Raises:
            ExportError: If torch is present but scripting/saving fails.
        """
        if not _torch_available():
            return SkippedExport(
                self.export_format, "PyTorch is not installed; export skipped."
            )
        return self._export_with_torch(model, destination)  # pragma: no cover

    def _export_with_torch(  # pragma: no cover - requires optional torch
        self, model: Any, destination: Path
    ) -> ExportRecord:
        """Perform the real TorchScript export (only runs when torch present)."""
        import torch

        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            scripted = torch.jit.script(model)
            scripted.save(str(destination))
        except Exception as exc:  # noqa: BLE001 - re-raised as a domain error
            raise ExportError(
                f"TorchScript export failed: {exc}",
                details={"destination": str(destination)},
            ) from exc
        return ExportRecord(
            export_format=self.export_format,
            status="exported",
            location=destination.as_posix(),
        )


class OnnxExporter:
    """Export a model to ONNX via ``torch.onnx.export``.

    Args:
        opset_version: The ONNX opset to target.
    """

    export_format = "onnx"

    def __init__(self, *, opset_version: int = 17) -> None:
        self.opset_version = opset_version

    def export(self, model: Any, destination: Path, **kwargs: Any) -> ExportRecord:
        """Export the model to ONNX at ``destination``.

        Args:
            model: The model object to export.
            destination: Path the ``.onnx`` file is written to.
            **kwargs: Accepts ``sample_input`` — a tensor used to trace the
                model. Ignored when the backend is unavailable.

        Returns:
            An :class:`ExportRecord`; ``skipped`` when torch/onnx are absent.

        Raises:
            ExportError: If the backend is present but export fails.
        """
        if not _torch_available():
            return SkippedExport(
                self.export_format, "PyTorch is not installed; export skipped."
            )
        if not _onnx_available():  # pragma: no cover - requires optional torch
            return SkippedExport(
                self.export_format, "onnx is not installed; export skipped."
            )
        return self._export_with_torch(  # pragma: no cover
            model, destination, sample_input=kwargs.get("sample_input")
        )

    def _export_with_torch(  # pragma: no cover - requires optional torch/onnx
        self, model: Any, destination: Path, *, sample_input: Any
    ) -> ExportRecord:
        """Perform the real ONNX export (only runs when the backend is present)."""
        import torch

        if sample_input is None:
            raise ExportError(
                "ONNX export requires a 'sample_input' tensor to trace the model.",
                details={"destination": str(destination)},
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            torch.onnx.export(
                model,
                sample_input,
                str(destination),
                opset_version=self.opset_version,
            )
        except Exception as exc:  # noqa: BLE001 - re-raised as a domain error
            raise ExportError(
                f"ONNX export failed: {exc}",
                details={"destination": str(destination)},
            ) from exc
        return ExportRecord(
            export_format=self.export_format,
            status="exported",
            location=destination.as_posix(),
        )


#: Registry of export-format identifier → exporter factory.
_EXPORTERS: dict[str, Any] = {
    "pytorch": PyTorchExporter,
    "torchscript": TorchScriptExporter,
    "onnx": OnnxExporter,
}


def get_exporter(export_format: str) -> ModelExporter:
    """Return an exporter instance for a named format.

    Args:
        export_format: One of :data:`SUPPORTED_EXPORT_FORMATS`.

    Returns:
        A ready-to-use :class:`ModelExporter`.

    Raises:
        UnsupportedExportFormatError: If ``export_format`` is unknown.
    """
    factory = _EXPORTERS.get(export_format.strip().lower())
    if factory is None:
        raise UnsupportedExportFormatError(
            f"Unsupported export format '{export_format}'. "
            f"Supported: {', '.join(SUPPORTED_EXPORT_FORMATS)}.",
            details={"format": export_format},
        )
    exporter: ModelExporter = factory()
    return exporter


@dataclass(frozen=True, slots=True)
class ExportPlan:
    """A resolved set of exports to attempt for one model.

    Attributes:
        model_name: Logical model name (used to build file names).
        version: Artifact version (used to build file names).
        formats: The export formats to attempt, in order.
    """

    model_name: str
    version: str
    formats: tuple[str, ...] = field(default_factory=lambda: SUPPORTED_EXPORT_FORMATS)


def export_model(
    model: Any,
    *,
    plan: ExportPlan,
    exports_dir: Path,
    sample_input: Any = None,
) -> list[ExportRecord]:
    """Attempt every export in ``plan``, returning one record per format.

    A missing backend yields a ``skipped`` record rather than aborting the
    remaining formats, so the caller always gets a complete outcome list.

    Args:
        model: The model object to export (may be ``None`` in the base env,
            where every format is skipped anyway).
        plan: The formats and naming to use.
        exports_dir: Directory the export files are written under.
        sample_input: Optional tracing input forwarded to the ONNX exporter.

    Returns:
        One :class:`ExportRecord` per requested format, in ``plan`` order.
    """
    suffixes = {"pytorch": ".pt", "torchscript": ".torchscript", "onnx": ".onnx"}
    records: list[ExportRecord] = []
    for fmt in plan.formats:
        exporter = get_exporter(fmt)
        suffix = suffixes.get(fmt, f".{fmt}")
        destination = exports_dir / f"{plan.model_name}-{plan.version}{suffix}"
        record = exporter.export(model, destination, sample_input=sample_input)
        if record.skipped:
            logger.info("Export '{}' skipped: {}", record.export_format, record.message)
        records.append(record)
    return records
