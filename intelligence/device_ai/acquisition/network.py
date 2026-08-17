"""Network connectivity detection — single check, never retried.

Online acquisition (remote adapters) needs egress. This module performs **one**
connectivity probe before any network work and classifies the result:

* :data:`ONLINE` — the probe succeeded;
* :data:`UNAVAILABLE` — the probe failed (no egress, DNS failure, timeout).
  The pipeline then continues in offline mode; **it never retries**;
* :data:`SKIPPED_OFFLINE` — the run was explicitly ``--mode offline`` so no
  probe was attempted at all.

The probe is dependency-injected (``probe=``) so tests exercise ONLINE /
UNAVAILABLE behaviour deterministically without ever opening a socket. The
default probe does a short-timeout TCP connect and is only ever invoked in
``auto``/``online`` modes.
"""

from __future__ import annotations

import socket
from collections.abc import Callable
from dataclasses import dataclass

# Statuses (stable, machine-readable).
ONLINE = "ONLINE"
UNAVAILABLE = "UNAVAILABLE"
SKIPPED_OFFLINE = "SKIPPED_OFFLINE"

# Default probe target: a public endpoint's TCP/443. Only reachability matters;
# no data is sent or received.
_DEFAULT_HOST = "1.1.1.1"
_DEFAULT_PORT = 443
_DEFAULT_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True, slots=True)
class ConnectivityResult:
    """Result of the single connectivity probe.

    Attributes:
        status: One of :data:`ONLINE`, :data:`UNAVAILABLE`, :data:`SKIPPED_OFFLINE`.
        probed: Whether a probe was actually attempted.
        target: The probe target (``host:port``) or an empty string when skipped.
        detail: Human-readable detail (e.g. the failure reason).
    """

    status: str
    probed: bool
    target: str
    detail: str

    @property
    def online(self) -> bool:
        """Whether egress is available."""
        return self.status == ONLINE

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "status": self.status,
            "probed": self.probed,
            "target": self.target,
            "detail": self.detail,
        }


def _default_probe(
    host: str = _DEFAULT_HOST,
    port: int = _DEFAULT_PORT,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
) -> bool:
    """Attempt a single short-timeout TCP connect; return success as a bool.

    Any failure (timeout, refused, DNS error, blocked egress) returns ``False``
    without raising. No payload is exchanged.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_connectivity(
    *,
    offline: bool,
    probe: Callable[[], bool] = _default_probe,
    target: str = f"{_DEFAULT_HOST}:{_DEFAULT_PORT}",
) -> ConnectivityResult:
    """Perform the single connectivity check (or skip it in offline mode).

    Args:
        offline: When ``True``, no probe is attempted (``SKIPPED_OFFLINE``).
        probe: Zero-arg callable returning ``True`` when egress is available;
            injected for testing. Invoked at most once.
        target: Display label for the probe target.

    Returns:
        A :class:`ConnectivityResult`. Never raises and never retries.
    """
    if offline:
        return ConnectivityResult(
            status=SKIPPED_OFFLINE,
            probed=False,
            target="",
            detail="offline mode requested; no network probe attempted",
        )

    try:
        reachable = probe()
    except Exception as exc:  # noqa: BLE001 - a probe must never crash the run
        return ConnectivityResult(
            status=UNAVAILABLE,
            probed=True,
            target=target,
            detail=f"probe raised {type(exc).__name__}: {exc}",
        )

    if reachable:
        return ConnectivityResult(
            status=ONLINE,
            probed=True,
            target=target,
            detail="connectivity probe succeeded",
        )
    return ConnectivityResult(
        status=UNAVAILABLE,
        probed=True,
        target=target,
        detail="connectivity probe failed; continuing offline (no retry)",
    )
