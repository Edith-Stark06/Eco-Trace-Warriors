"""Cross-cutting helpers for the training platform (milestone M1.3).

Small, dependency-light utilities shared across the training lifecycle:

* :mod:`git_utils` — resolve the current commit for run provenance.
* :mod:`seeding` — make a run deterministic (python / numpy / torch-if-present).
* :mod:`timing` — a :class:`~device_ai.training.utils.timing.Timer` context
  manager for wall-clock measurement.
* :mod:`env` — describe the compute device/backend for run records.

None of these import heavy ML frameworks unconditionally; torch is used only
when already installed, mirroring the optional-dependency policy of M1.1/M1.2.
"""

from __future__ import annotations

from .env import describe_environment, resolve_device
from .git_utils import git_commit_hash
from .seeding import seed_everything
from .timing import Timer

__all__ = [
    "Timer",
    "describe_environment",
    "git_commit_hash",
    "resolve_device",
    "seed_everything",
]
