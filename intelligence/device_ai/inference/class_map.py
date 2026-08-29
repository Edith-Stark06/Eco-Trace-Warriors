"""Canonical 8-class taxonomy for the EcoTrace e-waste object detector.

This module is the **single source of truth** for the class ID ↔ label
mapping shared by every detector implementation (single-model YOLO,
multi-model WBF ensemble, and any future variant).  Import from here
rather than re-declaring the mapping in each module.

The taxonomy was established during the P4.x research phase and is
frozen for production use.
"""

from __future__ import annotations

#: Mapping from integer class index to canonical lowercase label.
CANONICAL_CLASSES: dict[int, str] = {
    0: "laptop",
    1: "smartphone",
    2: "tablet",
    3: "monitor",
    4: "printer",
    5: "mouse",
    6: "camera",
    7: "headphones",
}

#: Total number of classes in the taxonomy.
NUM_CLASSES: int = len(CANONICAL_CLASSES)

#: Reverse mapping from canonical lowercase label to class index.
CLASS_NAME_TO_ID: dict[str, int] = {name: idx for idx, name in CANONICAL_CLASSES.items()}
