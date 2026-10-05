"""EcoID generation.

An EcoID is the human-readable public identifier assigned to every device
processed by the platform. Format (milestone spec):

    ET-YYYY-XXXXXXXX

* ``ET``       — fixed platform prefix.
* ``YYYY``     — four-digit year.
* ``XXXXXXXX`` — eight-character, zero-padded, upper-cased sequence derived
                 from an internal UUID so IDs are unique and non-guessable
                 while remaining compact.

A UUID is used internally (spec requirement) as the source of uniqueness;
the public suffix is a stable projection of that UUID. A monotonic counter
is offered as an alternative for demos where sequential IDs are desirable.
"""

from __future__ import annotations

import threading

from ..utils.hashing import new_uuid

# Fixed platform prefix for every EcoID.
_PREFIX = "ET"
# Width of the public numeric/hex suffix.
_SUFFIX_WIDTH = 8


class EcoIDGenerator:
    """Generate unique EcoIDs of the form ``ET-YYYY-XXXXXXXX``.

    Thread-safe: the internal counter is guarded by a lock so concurrent
    requests never receive the same sequential suffix.

    Args:
        year: Four-digit year embedded in generated IDs.
        sequence_start: First value used when generating sequential IDs.
    """

    def __init__(self, *, year: int, sequence_start: int = 1) -> None:
        if year < 1000 or year > 9999:
            raise ValueError("year must be a four-digit value")
        self._year = year
        self._counter = sequence_start
        self._lock = threading.Lock()

    def generate(self) -> str:
        """Generate a unique, non-sequential EcoID from an internal UUID.

        Returns:
            An EcoID string, e.g. ``"ET-2026-1A2B3C4D"``.
        """
        uuid_value = new_uuid()
        # Project the UUID into an 8-char upper-case hex suffix.
        suffix = f"{uuid_value.int % (16 ** _SUFFIX_WIDTH):0{_SUFFIX_WIDTH}X}"
        return self._format(suffix)

    def generate_sequential(self) -> str:
        """Generate a zero-padded sequential EcoID (useful for demos).

        Returns:
            An EcoID string, e.g. ``"ET-2026-00000001"``.
        """
        with self._lock:
            value = self._counter
            self._counter += 1
        return self._format(f"{value:0{_SUFFIX_WIDTH}d}")

    def _format(self, suffix: str) -> str:
        """Assemble the final EcoID string from a suffix."""
        return f"{_PREFIX}-{self._year}-{suffix}"
