"""Preflight — verify every frozen component before any data is touched.

The acquisition pipeline *borrows* frozen behaviour (taxonomy, duplicate
threshold, split ratios/seed, validators) and must never operate on a drifted
contract. This module reads the live values from their owning modules and
compares them with the expectations recorded in
:mod:`device_ai.acquisition.config`. Any mismatch aborts the run — the pipeline
refuses rather than silently acquiring against a changed taxonomy or a weakened
duplicate threshold.

It also fingerprints the **protected** data roots (P4.3.5 candidate, P4.3.6
expansion) so a run can prove, before and after, that it changed nothing there.
A fingerprint is the file count plus an aggregate SHA-256 over sorted
``relative_path:sha256`` lines — the same construction the frozen versioning
module uses for content addressing, computed here without importing it so
preflight stays cheap.

Nothing in this module writes to disk.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from .config import (
    EXPECTED_CLASS_ID,
    EXPECTED_HAMMING_THRESHOLD,
    EXPECTED_NUM_CLASSES,
    EXPECTED_SPLIT_RATIOS,
    EXPECTED_SPLIT_SEED,
    EXPECTED_TAXONOMY_VERSION,
    AcquisitionConfig,
)
from .provenance_model import compute_sha256

# Check verdicts (stable, machine-readable).
OK = "OK"
MISMATCH = "MISMATCH"
UNAVAILABLE = "UNAVAILABLE"

#: File suffixes counted when fingerprinting a protected tree.
_TRACKED_SUFFIXES = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".txt", ".json", ".csv", ".yaml", ".yml"}
)


@dataclass(frozen=True, slots=True)
class Check:
    """One preflight assertion.

    Attributes:
        name: Stable check identifier.
        verdict: :data:`OK`, :data:`MISMATCH` or :data:`UNAVAILABLE`.
        expected: The expected value, rendered as a string.
        actual: The observed value, rendered as a string.
        detail: Exact explanation (always populated on a non-OK verdict).
    """

    name: str
    verdict: str
    expected: str
    actual: str
    detail: str = ""

    @property
    def passed(self) -> bool:
        """Whether the check cleared."""
        return self.verdict == OK

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "name": self.name,
            "verdict": self.verdict,
            "expected": self.expected,
            "actual": self.actual,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class TreeFingerprint:
    """Content fingerprint of a protected directory tree.

    Attributes:
        label: Short identifier for the tree (e.g. ``p4_3_5_candidate``).
        path: POSIX path of the tree root.
        exists: Whether the root is present on disk.
        file_count: Number of tracked files found.
        image_count: Number of image files found.
        label_count: Number of YOLO ``.txt`` label files found.
        content_hash: Aggregate SHA-256 over sorted ``path:sha256`` lines
            (empty when the root is absent).
    """

    label: str
    path: str
    exists: bool
    file_count: int
    image_count: int
    label_count: int
    content_hash: str

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "label": self.label,
            "path": self.path,
            "exists": self.exists,
            "file_count": self.file_count,
            "image_count": self.image_count,
            "label_count": self.label_count,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """Aggregate preflight outcome.

    Attributes:
        checks: Every assertion performed, in execution order.
        fingerprints: Protected-tree fingerprints taken before the run.
        frozen_values: The live frozen values echoed for the report.
    """

    checks: list[Check] = field(default_factory=list)
    fingerprints: list[TreeFingerprint] = field(default_factory=list)
    frozen_values: dict[str, object] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Whether every check cleared."""
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> list[Check]:
        """The checks that did not clear."""
        return [check for check in self.checks if not check.passed]

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
            "failures": [check.name for check in self.failures],
            "protected_fingerprints": [f.to_dict() for f in self.fingerprints],
            "frozen_values": self.frozen_values,
        }


def fingerprint_tree(label: str, root: Path) -> TreeFingerprint:
    """Compute a content fingerprint of a protected tree (read-only).

    Args:
        label: Short identifier for the tree.
        root: Directory to fingerprint.

    Returns:
        A :class:`TreeFingerprint`. An absent root yields ``exists=False`` with
        zero counts and an empty hash — never a fabricated value.
    """
    if not root.is_dir():
        return TreeFingerprint(
            label=label,
            path=root.as_posix(),
            exists=False,
            file_count=0,
            image_count=0,
            label_count=0,
            content_hash="",
        )

    lines: list[str] = []
    images = 0
    labels = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in _TRACKED_SUFFIXES:
            continue
        rel = path.relative_to(root).as_posix()
        lines.append(f"{rel}:{compute_sha256(path)}")
        if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
            images += 1
        elif suffix == ".txt":
            labels += 1

    digest = hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()
    return TreeFingerprint(
        label=label,
        path=root.as_posix(),
        exists=True,
        file_count=len(lines),
        image_count=images,
        label_count=labels,
        content_hash=digest,
    )


def _taxonomy_checks() -> tuple[list[Check], dict[str, object]]:
    """Verify the frozen taxonomy contract and the target class id."""
    checks: list[Check] = []
    values: dict[str, object] = {}
    try:
        from ..dataset.taxonomy import load_taxonomy
    except Exception as exc:  # noqa: BLE001 - report, never crash preflight
        checks.append(
            Check(
                name="taxonomy_import",
                verdict=UNAVAILABLE,
                expected="device_ai.dataset.taxonomy.load_taxonomy importable",
                actual=f"{type(exc).__name__}: {exc}",
                detail="frozen taxonomy module could not be imported",
            )
        )
        return checks, values

    taxonomy = load_taxonomy()
    values["taxonomy_version"] = taxonomy.version
    values["num_classes"] = taxonomy.num_classes
    values["class_names"] = list(taxonomy.class_names)

    checks.append(
        Check(
            name="taxonomy_version",
            verdict=OK if taxonomy.version == EXPECTED_TAXONOMY_VERSION else MISMATCH,
            expected=EXPECTED_TAXONOMY_VERSION,
            actual=taxonomy.version,
            detail=(
                ""
                if taxonomy.version == EXPECTED_TAXONOMY_VERSION
                else "taxonomy version drifted from the frozen contract"
            ),
        )
    )
    checks.append(
        Check(
            name="taxonomy_num_classes",
            verdict=OK if taxonomy.num_classes == EXPECTED_NUM_CLASSES else MISMATCH,
            expected=str(EXPECTED_NUM_CLASSES),
            actual=str(taxonomy.num_classes),
            detail=(
                ""
                if taxonomy.num_classes == EXPECTED_NUM_CLASSES
                else "class count drifted from the frozen 19-class taxonomy"
            ),
        )
    )

    resolved = taxonomy.class_id_for("router")
    values["router_class_id"] = resolved
    checks.append(
        Check(
            name="target_class_id",
            verdict=OK if resolved == EXPECTED_CLASS_ID else MISMATCH,
            expected=f"router == {EXPECTED_CLASS_ID}",
            actual=f"router == {resolved}",
            detail=(
                ""
                if resolved == EXPECTED_CLASS_ID
                else (
                    "the taxonomy id for 'router' is not the expected 11; refusing "
                    "to acquire against a changed taxonomy"
                )
            ),
        )
    )
    return checks, values


def _settings_checks(settings: object | None) -> tuple[list[Check], dict[str, object]]:
    """Verify the frozen split ratios/seed and duplicate threshold.

    Args:
        settings: The settings object the pipeline will actually use. Passing the
            same instance is what makes this check meaningful — verifying the
            process-wide singleton while the run used a different object would
            leave the contract unenforced.
    """
    checks: list[Check] = []
    values: dict[str, object] = {}
    if settings is None:
        try:
            from ..configs.settings import get_settings
        except Exception as exc:  # noqa: BLE001 - report, never crash preflight
            checks.append(
                Check(
                    name="settings_import",
                    verdict=UNAVAILABLE,
                    expected="device_ai.configs.settings.get_settings importable",
                    actual=f"{type(exc).__name__}: {exc}",
                    detail="settings module could not be imported",
                )
            )
            return checks, values
        settings = get_settings()

    ratios = tuple(float(r) for r in settings.split_ratios)  # type: ignore[attr-defined]
    values["split_ratios"] = list(ratios)
    values["split_seed"] = int(settings.split_seed)  # type: ignore[attr-defined]
    values["duplicate_hamming_threshold"] = int(
        settings.duplicate_hamming_threshold  # type: ignore[attr-defined]
    )

    ratios_ok = all(
        abs(actual - expected) < 1e-9
        for actual, expected in zip(ratios, EXPECTED_SPLIT_RATIOS, strict=True)
    )
    checks.append(
        Check(
            name="split_ratios",
            verdict=OK if ratios_ok else MISMATCH,
            expected=str(list(EXPECTED_SPLIT_RATIOS)),
            actual=str(list(ratios)),
            detail="" if ratios_ok else "split ratios are not the frozen 70/20/10",
        )
    )
    seed_ok = int(settings.split_seed) == EXPECTED_SPLIT_SEED
    checks.append(
        Check(
            name="split_seed",
            verdict=OK if seed_ok else MISMATCH,
            expected=str(EXPECTED_SPLIT_SEED),
            actual=str(settings.split_seed),
            detail="" if seed_ok else "split seed is not the frozen 42",
        )
    )
    threshold_ok = int(settings.duplicate_hamming_threshold) == EXPECTED_HAMMING_THRESHOLD
    checks.append(
        Check(
            name="duplicate_hamming_threshold",
            verdict=OK if threshold_ok else MISMATCH,
            expected=str(EXPECTED_HAMMING_THRESHOLD),
            actual=str(settings.duplicate_hamming_threshold),
            detail=(
                ""
                if threshold_ok
                else (
                    "duplicate Hamming threshold drifted; refusing to run with a "
                    "weakened (or altered) duplicate detector"
                )
            ),
        )
    )
    return checks, values


#: Frozen collaborators the pipeline composes, as ``(check name, module, attr)``.
_FROZEN_COMPONENTS: tuple[tuple[str, str, str], ...] = (
    ("component_metadata_generator", "..dataset.metadata", "MetadataGenerator"),
    ("component_image_validator", "..dataset.image_validation", "ImageValidator"),
    ("component_annotation_validator", "..dataset.validator", "AnnotationValidator"),
    ("component_duplicate_detector", "..dataset.duplicates", "DuplicateDetector"),
    ("component_dataset_splitter", "..dataset.splitter", "DatasetSplitter"),
)


def _component_checks() -> list[Check]:
    """Verify every frozen collaborator resolves (dependency availability)."""
    from importlib import import_module

    checks: list[Check] = []
    for name, module_path, attribute in _FROZEN_COMPONENTS:
        try:
            module = import_module(module_path, package=__package__)
            resolved = getattr(module, attribute)
        except Exception as exc:  # noqa: BLE001 - report, never crash preflight
            checks.append(
                Check(
                    name=name,
                    verdict=UNAVAILABLE,
                    expected=f"{module_path.lstrip('.')}.{attribute}",
                    actual=f"{type(exc).__name__}: {exc}",
                    detail="frozen component unavailable (dependency missing?)",
                )
            )
            continue
        checks.append(
            Check(
                name=name,
                verdict=OK,
                expected=f"{module_path.lstrip('.')}.{attribute}",
                actual=resolved.__name__,
            )
        )
    return checks


def _path_checks(config: AcquisitionConfig) -> list[Check]:
    """Verify output paths are usable and never inside a protected tree."""
    checks: list[Check] = []
    protected = [root.resolve() for _, root in config.protected_roots]

    for name, path in (
        ("path_staging_root", config.staging_root),
        ("path_evidence_dir", config.evidence_dir),
        ("path_work_dir", config.work_dir),
        ("path_report", config.report_path.parent),
    ):
        resolved = path.resolve()
        inside = [p.as_posix() for p in protected if _is_within(resolved, p)]
        if inside:
            checks.append(
                Check(
                    name=name,
                    verdict=MISMATCH,
                    expected="outside every protected data root",
                    actual=resolved.as_posix(),
                    detail=(
                        "output path resolves inside a protected tree "
                        f"({', '.join(inside)}); refusing to run"
                    ),
                )
            )
            continue
        writable_parent = _nearest_existing_parent(resolved)
        checks.append(
            Check(
                name=name,
                verdict=OK,
                expected="creatable path outside protected data",
                actual=resolved.as_posix(),
                detail=f"nearest existing parent: {writable_parent.as_posix()}",
            )
        )
    return checks


def _is_within(candidate: Path, ancestor: Path) -> bool:
    """Whether ``candidate`` is ``ancestor`` or lies beneath it."""
    return candidate == ancestor or ancestor in candidate.parents


def _nearest_existing_parent(path: Path) -> Path:
    """Return the closest existing ancestor of ``path`` (or the path itself)."""
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def run_preflight(
    config: AcquisitionConfig, *, settings: object | None = None
) -> PreflightResult:
    """Verify frozen contracts, component availability and path safety.

    Args:
        config: The run layout whose output paths are checked.
        settings: The settings instance the run will use. Injecting the *same*
            object the pipeline uses is what makes the frozen-value assertions
            binding; ``None`` falls back to the process-wide singleton.

    Returns:
        A :class:`PreflightResult`. Callers must abort when
        :attr:`PreflightResult.passed` is ``False``.
    """
    checks: list[Check] = []
    values: dict[str, object] = {}

    taxonomy_checks, taxonomy_values = _taxonomy_checks()
    checks.extend(taxonomy_checks)
    values.update(taxonomy_values)

    settings_checks, settings_values = _settings_checks(settings)
    checks.extend(settings_checks)
    values.update(settings_values)

    checks.extend(_component_checks())
    checks.extend(_path_checks(config))

    fingerprints = [
        fingerprint_tree(label, root) for label, root in config.protected_roots
    ]
    return PreflightResult(
        checks=checks, fingerprints=fingerprints, frozen_values=values
    )


def compare_fingerprints(
    before: list[TreeFingerprint], after: list[TreeFingerprint]
) -> dict[str, object]:
    """Compare protected-tree fingerprints taken before and after a run.

    Args:
        before: Fingerprints captured by :func:`run_preflight`.
        after: Fingerprints captured after the pipeline finished.

    Returns:
        A primitive-only mapping with a per-tree verdict and an
        ``all_unchanged`` flag. A missing or added tree counts as *changed*.
    """
    before_by_label = {f.label: f for f in before}
    after_by_label = {f.label: f for f in after}
    trees: list[dict[str, object]] = []
    for label in sorted(set(before_by_label) | set(after_by_label)):
        start = before_by_label.get(label)
        end = after_by_label.get(label)
        if start is None or end is None:
            trees.append(
                {
                    "label": label,
                    "unchanged": False,
                    "detail": "fingerprint missing on one side of the comparison",
                }
            )
            continue
        unchanged = (
            start.exists == end.exists
            and start.file_count == end.file_count
            and start.content_hash == end.content_hash
        )
        trees.append(
            {
                "label": label,
                "path": start.path,
                "unchanged": unchanged,
                "exists": end.exists,
                "file_count_before": start.file_count,
                "file_count_after": end.file_count,
                "image_count": end.image_count,
                "label_count": end.label_count,
                "content_hash_before": start.content_hash,
                "content_hash_after": end.content_hash,
                "detail": (
                    "byte-identical (content hash and file count match)"
                    if unchanged
                    else "PROTECTED TREE CHANGED - investigate immediately"
                ),
            }
        )
    return {
        "all_unchanged": all(bool(t["unchanged"]) for t in trees),
        "trees": trees,
    }
