"""Tests for deterministic train/val/test splitting."""

from __future__ import annotations

import pytest

from device_ai.dataset.splitter import DatasetSplitter, split_to_dict
from device_ai.exceptions import EmptyDatasetError, InvalidSplitError


def _ids(n: int) -> list[str]:
    return [f"img_{i:03d}.png" for i in range(n)]


def test_split_counts_match_ratios():
    """A 100-item split honours the 70/20/10 proportions."""
    splitter = DatasetSplitter((0.7, 0.2, 0.1), seed=42)
    assignment = splitter.split_identifiers(_ids(100))
    assert assignment.counts == {"train": 70, "val": 20, "test": 10}


def test_split_is_deterministic():
    """The same identifiers and seed always yield identical partitions."""
    a = DatasetSplitter((0.7, 0.2, 0.1), seed=7).split_identifiers(_ids(50))
    b = DatasetSplitter((0.7, 0.2, 0.1), seed=7).split_identifiers(_ids(50))
    assert a.train == b.train
    assert a.val == b.val
    assert a.test == b.test


def test_split_is_order_independent():
    """Input ordering does not affect the resulting partition."""
    forward = DatasetSplitter((0.6, 0.2, 0.2), seed=1).split_identifiers(_ids(30))
    reversed_ids = list(reversed(_ids(30)))
    backward = DatasetSplitter((0.6, 0.2, 0.2), seed=1).split_identifiers(reversed_ids)
    assert forward.train == backward.train


def test_split_partitions_are_disjoint_and_complete():
    """Every identifier lands in exactly one split."""
    assignment = DatasetSplitter((0.7, 0.2, 0.1), seed=3).split_identifiers(_ids(40))
    combined = set(assignment.train) | set(assignment.val) | set(assignment.test)
    assert combined == set(_ids(40))
    assert len(assignment.train) + len(assignment.val) + len(assignment.test) == 40


def test_empty_dataset_raises():
    """Splitting an empty dataset raises EmptyDatasetError."""
    with pytest.raises(EmptyDatasetError):
        DatasetSplitter((0.7, 0.2, 0.1), seed=1).split_identifiers([])


def test_invalid_ratios_rejected():
    """Ratios that do not sum to 1.0 are rejected at construction."""
    with pytest.raises(InvalidSplitError):
        DatasetSplitter((0.5, 0.2, 0.1), seed=1)


def test_negative_ratios_rejected():
    """Negative ratios are rejected at construction."""
    with pytest.raises(InvalidSplitError):
        DatasetSplitter((1.2, -0.1, -0.1), seed=1)


def test_split_to_dict_shape():
    """The serialised split exposes ratios, seed, counts and members."""
    assignment = DatasetSplitter((0.7, 0.2, 0.1), seed=1).split_identifiers(_ids(10))
    payload = split_to_dict(assignment)
    assert payload["seed"] == 1
    assert payload["ratios"] == [0.7, 0.2, 0.1]
    assert set(payload["counts"]) == {"train", "val", "test"}
    assert isinstance(payload["train"], list)
