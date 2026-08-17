"""Source adapters for router acquisition.

Each adapter wraps one kind of source behind the uniform
:class:`~device_ai.acquisition.adapters.base.SourceAdapter` contract. The
**local archive** adapter is fully offline-capable; the remote adapters
(Roboflow, Kaggle, Hugging Face) *fail closed* when egress or credentials are
missing and never fabricate a candidate.
"""

from __future__ import annotations

from .base import (
    MECHANISM_HUGGINGFACE,
    MECHANISM_KAGGLE,
    MECHANISM_LOCAL_ARCHIVE,
    MECHANISM_ROBOFLOW,
    AdapterStatus,
    AdapterUnavailable,
    DiscoveryOutcome,
    SourceAdapter,
    SourceCandidate,
)
from .huggingface import HuggingFaceAdapter
from .kaggle import KaggleAdapter
from .local_archive import LocalArchiveAdapter
from .roboflow import RoboflowAdapter

__all__ = [
    "SourceAdapter",
    "SourceCandidate",
    "AdapterStatus",
    "AdapterUnavailable",
    "DiscoveryOutcome",
    "LocalArchiveAdapter",
    "RoboflowAdapter",
    "KaggleAdapter",
    "HuggingFaceAdapter",
    "MECHANISM_LOCAL_ARCHIVE",
    "MECHANISM_ROBOFLOW",
    "MECHANISM_KAGGLE",
    "MECHANISM_HUGGINGFACE",
]
