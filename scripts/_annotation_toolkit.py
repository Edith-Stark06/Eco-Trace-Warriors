"""Shared glue for the Phase 4.2.2 annotation toolkit.

The five annotation scripts — ``validate_annotations``,
``annotation_statistics``, ``visualize_annotations``, ``build_dataset_release``
and ``annotation_dashboard`` — live at repository top level under ``scripts/``
but reuse the **frozen** P4.1.2 dataset pipeline shipped in the ``device_ai``
package under ``intelligence/``. This module centralises the little the scripts
share so no logic is duplicated:

* the ``device_ai`` import bootstrap (re-exported from the P4.2.1
  ``_ecotrace_toolkit`` so the whole toolkit agrees on one ``sys.path`` setup),
* a single, line-numbered YOLO label reader used by both the validator's
  layered checks and the visualiser.

It adds **no** new domain logic to the pipeline: every parse still flows through
the frozen ``parse_yolo_line``. Nothing here mutates a label, an image or an API
surface.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

# Re-use the P4.2.1 bootstrap: importing REPO_ROOT prepends ``intelligence/`` to
# ``sys.path`` (idempotently) so ``import device_ai...`` works from the repo root.
from _ecotrace_toolkit import REPO_ROOT  # noqa: F401  (re-exported bootstrap)

from device_ai.dataset.validator import YoloBox, parse_yolo_line


def iter_label_boxes(path: Path) -> Iterator[tuple[int, YoloBox]]:
    """Yield ``(line_no, box)`` for every well-formed YOLO line in ``path``.

    Blank lines are skipped and malformed lines are silently ignored — the
    frozen :class:`~device_ai.dataset.validator.AnnotationValidator` is the
    single component that *reports* malformed lines; this reader only surfaces
    parseable geometry so downstream tools (layered checks, visualiser) never
    re-implement parsing.

    Args:
        path: Absolute path of a YOLO ``.txt`` label file.

    Yields:
        ``(line_no, box)`` pairs with ``line_no`` 1-based.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line_no, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            box = parse_yolo_line(stripped)
        except ValueError:
            continue
        yield line_no, box


def read_label_boxes(path: Path) -> list[YoloBox]:
    """Return the well-formed :class:`YoloBox` list from a label file.

    A thin wrapper over :func:`iter_label_boxes` for callers that do not need
    line numbers (e.g. rendering boxes onto a preview image).

    Args:
        path: Absolute path of a YOLO ``.txt`` label file.

    Returns:
        Every parseable bounding box, in file order.
    """
    return [box for _, box in iter_label_boxes(path)]
