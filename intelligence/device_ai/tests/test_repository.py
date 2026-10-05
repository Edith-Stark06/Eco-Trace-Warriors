"""Tests for the fingerprint persistence backends (milestone M1.5)."""

from pathlib import Path

import pytest

from device_ai.exceptions import FingerprintError
from device_ai.fingerprint.repository import (
    FingerprintRepository,
    InMemoryFingerprintRepository,
    JsonFileFingerprintRepository,
)


@pytest.fixture(params=["memory", "json"])
def repository(request: pytest.FixtureRequest, tmp_path: Path) -> FingerprintRepository:
    """Yield each repository implementation so tests run against both."""
    if request.param == "memory":
        return InMemoryFingerprintRepository()
    return JsonFileFingerprintRepository(tmp_path / "fingerprints")


def test_both_implementations_satisfy_the_protocol(repository):
    """Each concrete store is a structural :class:`FingerprintRepository`."""
    assert isinstance(repository, FingerprintRepository)


def test_save_then_get_round_trips(repository, sample_fingerprint):
    """A saved fingerprint is returned unchanged by ``get``."""
    repository.save(sample_fingerprint)
    restored = repository.get(sample_fingerprint.eco_id)
    assert restored == sample_fingerprint


def test_get_missing_returns_none(repository):
    """Fetching an unknown EcoID returns ``None`` rather than raising."""
    assert repository.get("ET-2026-DEADBEEF") is None


def test_exists_reflects_presence(repository, sample_fingerprint):
    """``exists`` is False before saving and True afterwards."""
    assert repository.exists(sample_fingerprint.eco_id) is False
    repository.save(sample_fingerprint)
    assert repository.exists(sample_fingerprint.eco_id) is True


def test_list_ids_returns_saved_ids(repository, sample_fingerprint):
    """``list_ids`` reports every stored EcoID."""
    assert repository.list_ids() == []
    repository.save(sample_fingerprint)
    assert repository.list_ids() == [sample_fingerprint.eco_id]


def test_save_overwrites_existing_record(repository, sample_fingerprint):
    """Saving twice with the same EcoID keeps a single (latest) record."""
    repository.save(sample_fingerprint)
    # Rebuild from a mutated dict to exercise the overwrite path cleanly.
    payload = sample_fingerprint.to_dict()
    payload["brand"] = "HP"
    updated = sample_fingerprint.from_dict(payload)
    repository.save(updated)
    assert repository.list_ids() == [sample_fingerprint.eco_id]
    assert repository.get(sample_fingerprint.eco_id).brand == "HP"


def test_json_repository_persists_to_disk(tmp_path: Path, sample_fingerprint):
    """The JSON backend writes a per-EcoID file that a new instance can read."""
    store_dir = tmp_path / "fingerprints"
    JsonFileFingerprintRepository(store_dir).save(sample_fingerprint)
    assert (store_dir / f"{sample_fingerprint.eco_id}.json").is_file()
    # A fresh instance pointed at the same directory sees the record.
    reopened = JsonFileFingerprintRepository(store_dir)
    assert reopened.get(sample_fingerprint.eco_id) == sample_fingerprint


def test_json_repository_list_ids_empty_when_dir_absent(tmp_path: Path):
    """``list_ids`` is empty (not an error) when the store dir does not exist."""
    repository = JsonFileFingerprintRepository(tmp_path / "missing")
    assert repository.list_ids() == []


@pytest.mark.parametrize("bad_id", ["", ".", "..", "a/b", "a\\b"])
def test_json_repository_rejects_path_traversal(tmp_path: Path, bad_id: str):
    """EcoIDs containing separators or dot names are refused."""
    repository = JsonFileFingerprintRepository(tmp_path / "fingerprints")
    with pytest.raises(FingerprintError):
        repository.exists(bad_id)
