"""Static configuration for the router-acquisition pipeline.

This module holds:

* The **target class** identity (``router``) and the *expected* frozen values
  used only as fail-closed guards — the authoritative values are always read at
  runtime from :func:`~device_ai.dataset.taxonomy.load_taxonomy` and
  :class:`~device_ai.configs.settings.Settings`. If the live values ever drift
  from these expectations the preflight refuses to run rather than silently
  operating on a changed taxonomy/threshold.
* An :class:`AcquisitionConfig` value object describing the filesystem layout
  (staging, evidence, report, protected candidate). All output paths default
  under the **git-ignored** ``dataset_acquisition/staging/`` and the review
  evidence directory; nothing is ever written into
  ``dataset_acquisition/candidate/`` (the protected data).

No heavy dependencies are imported here, so importing this module (and hence
the package) is cheap and side-effect free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# Target class + frozen-value expectations (guards, not sources of truth)
# --------------------------------------------------------------------------

#: Canonical taxonomy name for the class this wave acquires.
TARGET_CLASS_NAME = "router"

#: Expected taxonomy id for ``router`` (verified against ``load_taxonomy`` at
#: runtime; a mismatch aborts rather than proceeding on a changed taxonomy).
EXPECTED_CLASS_ID = 11

#: Expected frozen taxonomy shape.
EXPECTED_NUM_CLASSES = 19
EXPECTED_TAXONOMY_VERSION = "1.0.0"

#: Expected frozen pipeline constants (verified against ``Settings``).
EXPECTED_HAMMING_THRESHOLD = 5
EXPECTED_SPLIT_RATIOS = (0.7, 0.2, 0.1)
EXPECTED_SPLIT_SEED = 42

#: Wave identifier used for the staging sub-tree name.
WAVE_ID = "p4_3_7_expansion_v1"


def repo_root() -> Path:
    """Return the repository root (``Eco-Trace-Warriors/``).

    The package lives at ``intelligence/device_ai/acquisition/``; the root is
    three levels up from this file's package directory.
    """
    return Path(__file__).resolve().parents[3]


#: Read-only protected data roots, relative to ``dataset_acquisition/``. These
#: are scanned for cross-batch deduplication and fingerprinted before/after every
#: run; the pipeline never writes beneath them.
PROTECTED_ROOTS: tuple[tuple[str, str], ...] = (
    ("p4_3_5_candidate", "candidate/p4_3_5_dataset_v1_candidate"),
    ("p4_3_6_expansion", "staging/p4_3_6_expansion_v1"),
)


@dataclass(frozen=True, slots=True)
class AcquisitionConfig:
    """Filesystem layout and target identity for one acquisition run.

    Attributes:
        target_class: Canonical taxonomy class name to acquire.
        wave_id: Staging sub-tree name for this wave.
        staging_root: Batch root under the git-ignored ``staging/`` tree; holds
            ``images/`` and ``labels/`` written by the pipeline.
        evidence_dir: Review directory for JSON evidence + provenance manifest.
        report_path: Markdown automation report destination.
        json_report_path: Machine-readable run report destination.
        work_dir: Scratch directory for archive extraction and remote downloads
            (git-ignored; never the protected or staged batch tree).
        protected_roots: Read-only protected data roots as ``(label, path)``
            pairs. They are deduplicated against and fingerprinted, never
            written to. Absent roots are reported, never fabricated.
    """

    target_class: str = TARGET_CLASS_NAME
    wave_id: str = WAVE_ID
    staging_root: Path = field(default_factory=Path)
    evidence_dir: Path = field(default_factory=Path)
    report_path: Path = field(default_factory=Path)
    json_report_path: Path = field(default_factory=Path)
    work_dir: Path = field(default_factory=Path)
    protected_roots: tuple[tuple[str, Path], ...] = ()

    @property
    def images_root(self) -> Path:
        """Directory holding staged (accepted) images."""
        return self.staging_root / "images"

    @property
    def labels_root(self) -> Path:
        """Directory holding staged YOLO labels mirroring the images."""
        return self.staging_root / "labels"

    @property
    def provenance_path(self) -> Path:
        """JSON provenance manifest destination (superset records)."""
        return self.evidence_dir / "provenance_manifest.json"

    @classmethod
    def default(cls, *, root: Path | None = None) -> AcquisitionConfig:
        """Build the standard P4.3.7 layout rooted at the repository.

        Args:
            root: Repository root override (defaults to the detected root).

        Returns:
            A fully-populated :class:`AcquisitionConfig`.
        """
        base = root or repo_root()
        acq = base / "dataset_acquisition"
        review = acq / "review" / "p4_3_7_source_expansion"
        return cls(
            target_class=TARGET_CLASS_NAME,
            wave_id=WAVE_ID,
            staging_root=acq / "staging" / WAVE_ID / "router",
            evidence_dir=review / "router_automation",
            report_path=review / "P4_3_7_ROUTER_AUTOMATION_REPORT.md",
            json_report_path=review / "router_automation" / "run_report.json",
            work_dir=acq / "staging" / WAVE_ID / "_work",
            protected_roots=tuple(
                (label, acq / relative) for label, relative in PROTECTED_ROOTS
            ),
        )
