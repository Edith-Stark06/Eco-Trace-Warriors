"""Compute-environment description for run provenance.

These helpers answer "what did this run execute on?" without assuming any ML
framework is installed. When PyTorch is present they report the real device and
CUDA details; in the base environment they degrade to an honest CPU description
built from the standard library alone.
"""

from __future__ import annotations

import platform
import sys


def resolve_device(requested: str = "auto") -> str:
    """Resolve a requested device selector to a concrete device string.

    ``"auto"`` selects CUDA when torch reports it available, otherwise CPU. An
    explicit ``"cuda"``/``"cpu"`` request is honoured verbatim (validation of
    availability is left to the trainer). Without torch, everything resolves to
    ``"cpu"``.

    Args:
        requested: One of ``"auto"``, ``"cpu"`` or ``"cuda"``.

    Returns:
        The resolved device string (``"cpu"`` or ``"cuda"``).
    """
    normalized = requested.strip().lower()
    if normalized == "cpu":
        return "cpu"

    cuda = _cuda_available()
    if normalized == "cuda":
        return "cuda" if cuda else "cpu"
    # "auto" (and any unrecognised value) prefers CUDA when present.
    return "cuda" if cuda else "cpu"


def _cuda_available() -> bool:
    """Return whether a CUDA device is available via torch (if installed)."""
    try:  # pragma: no cover - torch is not installed in the base environment
        import torch
    except ImportError:
        return False
    return bool(torch.cuda.is_available())  # pragma: no cover


def _gpu_name() -> str:
    """Return the primary CUDA device name, or an empty string when none."""
    try:  # pragma: no cover - torch is not installed in the base environment
        import torch
    except ImportError:
        return ""
    if not torch.cuda.is_available():  # pragma: no cover
        return ""
    return str(torch.cuda.get_device_name(0))  # pragma: no cover


def _torch_version() -> str:
    """Return the installed torch version, or an empty string when absent."""
    try:  # pragma: no cover - torch is not installed in the base environment
        import torch
    except ImportError:
        return ""
    return str(torch.__version__)  # pragma: no cover


def describe_environment(requested_device: str = "auto") -> dict[str, str]:
    """Return a primitive-only description of the run's compute environment.

    The result is JSON-serialisable and embedded verbatim in experiment and
    model-registry records so every run carries its own provenance.

    Args:
        requested_device: The device selector from the run configuration.

    Returns:
        A mapping with keys ``device``, ``gpu``, ``python``, ``platform``,
        ``processor`` and ``torch`` (empty strings where a value is unknown or
        the optional dependency is absent).
    """
    device = resolve_device(requested_device)
    return {
        "device": device,
        "gpu": _gpu_name(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "torch": _torch_version(),
        "executable": sys.executable,
    }
