"""Source-adapter interface and shared value objects.

Every acquisition source (a local archive, Roboflow, Kaggle, Hugging Face) is
wrapped by a :class:`SourceAdapter` exposing a uniform metadata contract and a
two-phase lifecycle:

* :meth:`SourceAdapter.availability` — a fail-closed check of prerequisites
  (inputs / credentials / network). Remote adapters report *unavailable* (they
  never guess) when egress or credentials are missing.
* :meth:`SourceAdapter.discover` — return candidate :class:`SourceCandidate`
  metadata **without downloading**.
* :meth:`SourceAdapter.materialize` — ensure a candidate's data is on local
  disk and return its root, so the identical local-ingestion path runs for
  every source.

Adapters never fabricate a source: with no configured coordinates and no
egress, discovery legitimately yields nothing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import AcquisitionError

# Download-mechanism identifiers.
MECHANISM_LOCAL_ARCHIVE = "local-archive"
MECHANISM_ROBOFLOW = "roboflow-api"
MECHANISM_KAGGLE = "kaggle-api"
MECHANISM_HUGGINGFACE = "huggingface-datasets"


class AdapterUnavailable(AcquisitionError):
    """Raised when an adapter cannot operate (missing inputs/creds/network).

    This is the *fail-closed* signal: the pipeline records it as a rejected /
    skipped source with the exact reason and continues — it never becomes a
    fabricated result.
    """

    code = "ACQUISITION_ADAPTER_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class AdapterStatus:
    """Whether an adapter can run, and why not when it cannot.

    Attributes:
        available: Whether the adapter's prerequisites are satisfied.
        reason: Human/machine-readable explanation.
        missing_requirements: Sorted requirement keys that are unmet
            (e.g. ``("network", "credentials")``).
    """

    available: bool
    reason: str
    missing_requirements: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "available": self.available,
            "reason": self.reason,
            "missing_requirements": list(self.missing_requirements),
        }


@dataclass(frozen=True, slots=True)
class SourceCandidate:
    """Uniform metadata describing one candidate source (§2 interface).

    Attributes:
        name: Dataset name.
        publisher: Publisher / owner.
        url: Source URL (empty for a purely local archive).
        version: Dataset version identifier.
        license_raw: License string exactly as supplied by the source.
        license_url: Supporting license URL, if any.
        source_class: The source's own class label(s) relevant to the target.
        bbox_available: Whether the source carries bounding boxes (not merely
            image-classification tags).
        image_identifier: How images are identified in the source.
        annotation_identifier: How annotations are identified in the source.
        download_mechanism: One of the ``MECHANISM_*`` identifiers.
        adapter: Name of the adapter that produced this candidate.
        local_root: Local directory once materialised (empty until then).
        detail: Free-form note (e.g. detected format description).
    """

    name: str
    publisher: str
    url: str
    version: str
    license_raw: str
    license_url: str
    source_class: str
    bbox_available: bool
    image_identifier: str
    annotation_identifier: str
    download_mechanism: str
    adapter: str
    local_root: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "name": self.name,
            "publisher": self.publisher,
            "url": self.url,
            "version": self.version,
            "license_raw": self.license_raw,
            "license_url": self.license_url,
            "source_class": self.source_class,
            "bbox_available": self.bbox_available,
            "image_identifier": self.image_identifier,
            "annotation_identifier": self.annotation_identifier,
            "download_mechanism": self.download_mechanism,
            "adapter": self.adapter,
            "local_root": self.local_root,
            "detail": self.detail,
        }


class SourceAdapter(ABC):
    """Abstract base for all acquisition source adapters."""

    #: Stable adapter name (also the ``adapter`` field on candidates).
    name: str = "abstract"

    @abstractmethod
    def availability(self, *, online: bool) -> AdapterStatus:
        """Return a fail-closed prerequisite check.

        Args:
            online: Whether egress is available this run.
        """

    @abstractmethod
    def discover(self, *, online: bool) -> list[SourceCandidate]:
        """Return candidate metadata without downloading.

        Raises:
            AdapterUnavailable: If prerequisites are unmet for a remote source.
        """

    @abstractmethod
    def materialize(self, candidate: SourceCandidate, *, online: bool) -> Path:
        """Ensure the candidate's data is on local disk; return its root.

        Raises:
            AdapterUnavailable: If prerequisites are unmet.
        """


@dataclass(frozen=True, slots=True)
class DiscoveryOutcome:
    """Aggregate result of running discovery across all adapters.

    Attributes:
        candidates: Every discovered candidate.
        adapter_statuses: Per-adapter availability (name -> status dict).
    """

    candidates: list[SourceCandidate] = field(default_factory=list)
    adapter_statuses: dict[str, dict] = field(default_factory=dict)
