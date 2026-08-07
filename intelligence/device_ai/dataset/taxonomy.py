"""Canonical device-detection taxonomy accessor (Sprint P4.1.2).

The 19-class device-detection taxonomy is defined once, in the component
profile library (``components/data/components.yaml``). This module reads the
class names and version *from that single source of truth* so the dataset
pipeline never hardcodes the class list or its ordering. The insertion order of
the profile library is the canonical class-ID ordering (0 → 18).

Keeping this as a thin read-only accessor honours the "no duplicated
functionality" rule: the taxonomy lives in the components engine; the dataset
tooling merely borrows its class names and version for statistics and
versioning.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..components.profiles import load_library

# The component library is packaged relative to the ``device_ai`` root.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_LIBRARY_PATH = _PACKAGE_ROOT / "components" / "data" / "components.yaml"


@dataclass(frozen=True, slots=True)
class DeviceTaxonomy:
    """The canonical device-detection class taxonomy.

    Attributes:
        version: Semantic version of the taxonomy (mirrors the component
            catalogue version, e.g. ``"1.0.0"``).
        class_names: Ordered class names; the list index is the YOLO class id.
    """

    version: str
    class_names: tuple[str, ...]

    @property
    def num_classes(self) -> int:
        """Number of classes in the taxonomy."""
        return len(self.class_names)

    def name_for(self, class_id: int) -> str:
        """Return the class name for a class id, or ``"unknown"`` if unmapped.

        Args:
            class_id: The YOLO integer class id.

        Returns:
            The canonical class name, or ``"unknown"`` when out of range.
        """
        if 0 <= class_id < len(self.class_names):
            return self.class_names[class_id]
        return "unknown"

    def class_id_for(self, name: str) -> int | None:
        """Return the class id for a class name, or ``None`` if unknown.

        Args:
            name: A canonical class name.

        Returns:
            The zero-based class id, or ``None`` when the name is not in the
            taxonomy.
        """
        try:
            return self.class_names.index(name)
        except ValueError:
            return None


def load_taxonomy(library_path: str | Path | None = None) -> DeviceTaxonomy:
    """Load the canonical device taxonomy from the component library.

    Args:
        library_path: Optional path to the component profile library. Defaults
            to the packaged ``components/data/components.yaml``.

    Returns:
        The :class:`DeviceTaxonomy` with its version and ordered class names.
    """
    path = Path(library_path) if library_path is not None else _DEFAULT_LIBRARY_PATH
    library = load_library(path)
    return DeviceTaxonomy(
        version=library.version,
        class_names=tuple(library.profiles.keys()),
    )
