"""Unit tests for the blockchain ledger config and loader (milestone M3.1).

Exercises :func:`load_config` and :class:`LedgerConfig`: the shipped external
YAML loads and validates, malformed files raise the typed
:class:`LedgerConfigError`, and the config object resolves relative paths and
maps from settings. Mirrors the M2.5 trust-rules loader test structure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from device_ai.exceptions import LedgerConfigError
from device_ai.ledger.config import (
    DEFAULT_BLOCKCHAIN_VERSION,
    DEFAULT_HASH_ALGORITHM,
    GENESIS_PREVIOUS_HASH,
    LedgerConfig,
    load_config,
)

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _shipped_path() -> Path:
    return LedgerConfig().resolved_config_path(package_root=_PACKAGE_ROOT)


def _write(tmp_path: Path, text: str, *, name: str = "ledger.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --- Shipped catalogue -----------------------------------------------------


def test_shipped_config_loads_and_validates():
    config = load_config(_shipped_path())
    assert config.hash_algorithm == "sha256"
    assert config.blockchain_version
    assert len(config.genesis_previous_hash) == 64


def test_defaults_match_module_constants():
    config = LedgerConfig()
    assert config.hash_algorithm == DEFAULT_HASH_ALGORITHM
    assert config.blockchain_version == DEFAULT_BLOCKCHAIN_VERSION
    assert config.genesis_previous_hash == GENESIS_PREVIOUS_HASH


# --- Path resolution -------------------------------------------------------


def test_relative_path_resolves_against_package_root():
    config = LedgerConfig(config_path="ledger/data/ledger.yaml")
    resolved = config.resolved_config_path(package_root=_PACKAGE_ROOT)
    assert resolved.is_absolute()
    assert resolved.exists()


def test_absolute_path_is_returned_unchanged(tmp_path: Path):
    absolute = tmp_path / "abs.yaml"
    config = LedgerConfig(config_path=str(absolute))
    assert config.resolved_config_path(package_root=_PACKAGE_ROOT) == absolute


# --- Valid custom files ----------------------------------------------------


def test_custom_yaml_loads(tmp_path: Path):
    path = _write(
        tmp_path,
        """
version: "2.0.0"
hash_algorithm: "sha3_256"
blockchain_version: "3.1.4"
genesis_previous_hash: "abcdef0123456789"
""",
    )
    config = load_config(path)
    assert config.hash_algorithm == "sha3_256"
    assert config.blockchain_version == "3.1.4"
    assert config.genesis_previous_hash == "abcdef0123456789"


def test_json_config_loads(tmp_path: Path):
    path = _write(
        tmp_path,
        '{"version": "1.0.0", "hash_algorithm": "sha512"}',
        name="ledger.json",
    )
    config = load_config(path)
    assert config.hash_algorithm == "sha512"
    # Omitted fields fall back to defaults.
    assert config.blockchain_version == DEFAULT_BLOCKCHAIN_VERSION


# --- Malformed files raise -------------------------------------------------


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(LedgerConfigError):
        load_config(tmp_path / "nope.yaml")


def test_empty_file_raises(tmp_path: Path):
    with pytest.raises(LedgerConfigError):
        load_config(_write(tmp_path, ""))


def test_non_mapping_root_raises(tmp_path: Path):
    with pytest.raises(LedgerConfigError):
        load_config(_write(tmp_path, "- a\n- b\n"))


def test_missing_version_raises(tmp_path: Path):
    with pytest.raises(LedgerConfigError):
        load_config(_write(tmp_path, 'hash_algorithm: "sha256"\n'))


def test_unsupported_hash_algorithm_raises(tmp_path: Path):
    with pytest.raises(LedgerConfigError):
        load_config(
            _write(tmp_path, 'version: "1.0.0"\nhash_algorithm: "not_a_real_hash"\n')
        )


def test_empty_hash_algorithm_raises(tmp_path: Path):
    with pytest.raises(LedgerConfigError):
        load_config(_write(tmp_path, 'version: "1.0.0"\nhash_algorithm: "  "\n'))


def test_non_hex_genesis_raises(tmp_path: Path):
    with pytest.raises(LedgerConfigError):
        load_config(
            _write(
                tmp_path,
                'version: "1.0.0"\ngenesis_previous_hash: "not-hex-zzz"\n',
            )
        )


def test_from_settings_returns_defaults():
    from device_ai.configs.settings import Settings

    config = LedgerConfig.from_settings(Settings())
    assert config.hash_algorithm == DEFAULT_HASH_ALGORITHM
