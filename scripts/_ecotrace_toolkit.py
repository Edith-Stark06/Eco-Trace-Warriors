"""Shared glue for the Phase 4.2.1 dataset collection toolkit.

The four toolkit scripts — ``validate_image_batch``, ``dataset_progress``,
``merge_collection_batches`` and ``collection_dashboard`` — live at repository
top level under ``scripts/`` but reuse the **frozen** P4.1.2 dataset pipeline
shipped in the ``device_ai`` package under ``intelligence/``. This module
centralises the small amount of code they share so no logic is duplicated:

* locating and importing the ``device_ai`` package (``sys.path`` bootstrap),
* parsing the collection **filename convention**
  ``<class_name>_<source_tag>_<seq>.<ext>`` against the code-owned taxonomy,
* discovering images and loading settings + taxonomy through the existing API.

It adds **no** new domain logic to the pipeline: every image metric, hash,
duplicate check and provenance record still comes from the existing modules.
This module never mutates the dataset and touches no API surface.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# --- device_ai import bootstrap -------------------------------------------
# The scripts are launched as plain files from the repo root, so the
# ``device_ai`` package (under ``intelligence/``) is not importable by default.
# Prepend that directory to ``sys.path`` exactly once, without mutating the
# caller's environment or requiring an editable install.
REPO_ROOT = Path(__file__).resolve().parents[1]
_INTELLIGENCE_ROOT = REPO_ROOT / "intelligence"

if _INTELLIGENCE_ROOT.is_dir() and str(_INTELLIGENCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_INTELLIGENCE_ROOT))


@dataclass(frozen=True, slots=True)
class ParsedFilename:
    """Result of parsing a filename against the collection convention.

    The convention (``docs/ai/templates/image_inventory.csv``) is
    ``<class_name>_<source_tag>_<seq>.<ext>`` where ``class_name`` is a
    canonical taxonomy class (which may itself contain underscores, e.g.
    ``crt_monitor``), ``source_tag`` is an alphanumeric origin tag and ``seq``
    is a zero-padded numeric sequence.

    Attributes:
        class_name: The matched taxonomy class, or ``None`` when unmatched.
        source_tag: The parsed source tag, or ``None`` when unparsed.
        sequence: The parsed numeric sequence string, or ``None``.
        is_valid: Whether the filename fully satisfies the convention.
        reason: Human-readable explanation when ``is_valid`` is ``False``.
    """

    class_name: str | None
    source_tag: str | None
    sequence: str | None
    is_valid: bool
    reason: str


def parse_collection_filename(
    filename: str, class_names: tuple[str, ...]
) -> ParsedFilename:
    """Parse ``filename`` against ``<class_name>_<source_tag>_<seq>``.

    Class names may contain underscores, so the longest class name that is a
    prefix of the stem wins (``crt_monitor`` beats ``monitor``). The remainder
    is split on its final underscore into ``source_tag`` and ``seq``.

    Args:
        filename: A bare file name (with or without directory components).
        class_names: The canonical taxonomy class names (code-owned order).

    Returns:
        A :class:`ParsedFilename` describing the outcome.
    """
    stem = Path(filename).stem
    prefixes = [c for c in class_names if stem == c or stem.startswith(f"{c}_")]
    if not prefixes:
        return ParsedFilename(None, None, None, False, "no known taxonomy class prefix")

    class_name = max(prefixes, key=len)
    remainder = stem[len(class_name) :]
    if not remainder.startswith("_"):
        return ParsedFilename(
            class_name, None, None, False, "missing source_tag and sequence"
        )

    parts = remainder[1:].rsplit("_", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return ParsedFilename(
            class_name,
            None,
            None,
            False,
            "expected <class_name>_<source_tag>_<seq>",
        )

    source_tag, sequence = parts
    if not sequence.isdigit():
        return ParsedFilename(
            class_name, source_tag, sequence, False, "sequence must be numeric"
        )
    if not source_tag.isalnum():
        return ParsedFilename(
            class_name, source_tag, sequence, False, "source_tag must be alphanumeric"
        )
    return ParsedFilename(class_name, source_tag, sequence, True, "")


def class_from_filename(filename: str, class_names: tuple[str, ...]) -> str | None:
    """Return the taxonomy class inferred from ``filename``, or ``None``.

    A thin wrapper over :func:`parse_collection_filename` that yields just the
    class name even when the rest of the convention is malformed, so counting
    tools can still bucket a partially-named file by its class prefix.

    Args:
        filename: A bare file name.
        class_names: The canonical taxonomy class names.

    Returns:
        The matched class name, or ``None`` when no class prefix matched.
    """
    return parse_collection_filename(filename, class_names).class_name
