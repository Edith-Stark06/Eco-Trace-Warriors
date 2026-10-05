"""Static configuration for the multi-class acquisition pipeline.

This module holds:

* The **default target class** identity (``router``) and the *expected* frozen
  values used only as fail-closed guards — the authoritative values are always
  read at runtime from :func:`~device_ai.dataset.taxonomy.load_taxonomy` and
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

import os
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


def dataset_acquisition_root(*, root: Path | None = None) -> Path:
    """Resolve the ``dataset_acquisition/`` tree's actual location.

    The ~29GB of acquired training/staging/evaluation data was migrated
    (2026-09) to an external drive to keep it out of the repository. If
    ``ECOTRACE_DATASET_ROOT`` is set, it wins; otherwise this falls back to
    ``<repo_root>/dataset_acquisition`` — the original in-repo layout, so a
    machine that still has the data there (or a fresh clone that hasn't
    migrated yet) keeps working unchanged. Callers that need the data to
    exist should check for it themselves and fail with a clear message
    naming the resolved path — this function only resolves the root, it
    never validates it.

    An explicit ``root`` always wins over ``ECOTRACE_DATASET_ROOT``: passing
    ``root`` means "resolve as if this were the repository root" (test
    isolation — e.g. a sandboxed ``tmp_path``), a different, more specific
    intent than "the dataset lives at this absolute location regardless of
    repo root". Honoring the env var over an explicit root would silently
    point a sandboxed test at the real external dataset.

    Args:
        root: Repository root override. When given, resolves under it
            directly and ``ECOTRACE_DATASET_ROOT`` is not consulted.

    Returns:
        The resolved dataset_acquisition root, absolute.
    """
    if root is not None:
        return root / "dataset_acquisition"
    override = os.environ.get("ECOTRACE_DATASET_ROOT")
    if override:
        return Path(override)
    return repo_root() / "dataset_acquisition"


#: Read-only protected data roots, relative to ``dataset_acquisition/``. These
#: are scanned for cross-batch deduplication and fingerprinted before/after every
#: run; the pipeline never writes beneath them.
PROTECTED_ROOTS: tuple[tuple[str, str], ...] = (
    ("p4_3_5_candidate", "candidate/p4_3_5_dataset_v1_candidate"),
    ("p4_3_6_expansion", "staging/p4_3_6_expansion_v1"),
)


@dataclass(frozen=True, slots=True)
class TargetClass:
    """A validated acquisition target resolved against the frozen taxonomy.

    The taxonomy in ``components/data/components.yaml`` is the single source of
    truth; this value object never duplicates the class list. Construct instances
    via :meth:`resolve` (by name and/or id) or :meth:`parse` (a CLI token) so
    invalid classes fail cleanly instead of silently acquiring the wrong data.

    Attributes:
        name: Canonical taxonomy class name (e.g. ``laptop``).
        class_id: The class's frozen taxonomy id.
    """

    name: str
    class_id: int

    @classmethod
    def resolve(
        cls,
        *,
        name: str | None = None,
        class_id: int | None = None,
        taxonomy: object | None = None,
    ) -> TargetClass:
        """Resolve and validate a target class against the frozen taxonomy.

        Args:
            name: Canonical class name, if known.
            class_id: Class id, if known.
            taxonomy: Optional pre-loaded taxonomy (defaults to ``load_taxonomy``).

        Returns:
            A validated :class:`TargetClass`.

        Raises:
            ValueError: If neither identifier is given, the name is unknown, the
                id is out of range, or the two disagree.
        """
        if taxonomy is None:
            from ..dataset.taxonomy import load_taxonomy

            taxonomy = load_taxonomy()
        class_names = tuple(getattr(taxonomy, "class_names", ()))
        n = len(class_names)

        if name is None and class_id is None:
            raise ValueError("target class requires a name or a class id")

        resolved_name: str | None = None
        resolved_id: int | None = None
        if name is not None:
            if name not in class_names:
                raise ValueError(
                    f"unknown target class name '{name}': not in the frozen "
                    f"{n}-class taxonomy"
                )
            resolved_name = name
            resolved_id = class_names.index(name)
        if class_id is not None:
            if not 0 <= class_id < n:
                raise ValueError(
                    f"target class id {class_id} out of range for the frozen "
                    f"{n}-class taxonomy (0..{n - 1})"
                )
            id_name = class_names[class_id]
            if resolved_name is not None and id_name != resolved_name:
                raise ValueError(
                    f"inconsistent target class: name '{resolved_name}' is id "
                    f"{resolved_id}, not {class_id}"
                )
            resolved_name = id_name
            resolved_id = class_id

        assert resolved_name is not None and resolved_id is not None
        return cls(name=resolved_name, class_id=int(resolved_id))

    @classmethod
    def parse(cls, token: str, *, taxonomy: object | None = None) -> TargetClass:
        """Resolve a CLI token that is either a class name or an integer id.

        Args:
            token: A class name (``laptop``) or a stringified id (``0``).
            taxonomy: Optional pre-loaded taxonomy.

        Returns:
            A validated :class:`TargetClass`.

        Raises:
            ValueError: If the token is empty or does not resolve.
        """
        text = (token or "").strip()
        if not text:
            raise ValueError("empty target class")
        if text.isdigit():
            return cls.resolve(class_id=int(text), taxonomy=taxonomy)
        return cls.resolve(name=text, taxonomy=taxonomy)


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
        acq = dataset_acquisition_root(root=root)
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

    @classmethod
    def for_target(
        cls,
        target: TargetClass,
        *,
        root: Path | None = None,
        wave_id: str | None = None,
    ) -> AcquisitionConfig:
        """Build a layout for an arbitrary taxonomy target class (P4.3.8).

        The ``router`` target on the default wave delegates to :meth:`default`
        so the P4.3.7 router layout is preserved byte-for-byte. Any other class
        gets a parallel layout under the git-ignored staging tree and a
        per-class review directory. Protected roots are unchanged, and no output
        path is ever placed beneath them.

        Args:
            target: The validated target class.
            root: Repository root override (defaults to the detected root).
            wave_id: Staging sub-tree name (defaults to :data:`WAVE_ID`).

        Returns:
            A fully-populated :class:`AcquisitionConfig`.
        """
        wave = wave_id or WAVE_ID
        if target.name == TARGET_CLASS_NAME and wave == WAVE_ID:
            return cls.default(root=root)

        acq = dataset_acquisition_root(root=root)
        review = acq / "review" / "p4_3_8_multiclass_acquisition" / target.name
        return cls(
            target_class=target.name,
            wave_id=wave,
            staging_root=acq / "staging" / wave / target.name,
            evidence_dir=review / "automation",
            report_path=review / f"P4_3_8_{target.name.upper()}_ACQUISITION_REPORT.md",
            json_report_path=review / "automation" / "run_report.json",
            work_dir=acq / "staging" / wave / "_work",
            protected_roots=tuple(
                (label, acq / relative) for label, relative in PROTECTED_ROOTS
            ),
        )
