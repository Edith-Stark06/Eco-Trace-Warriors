"""Configuration and external loader for the blockchain ledger core (M3.1).

Mirrors the trust, integrity and passport engines' configs: a small, frozen,
slotted value object holding the ledger builder's operational knobs, plus a
strict validating loader that turns an external YAML/JSON file into that
immutable value object.

The ledger's operational policy — *which hash algorithm anchors blocks, which
version tag brands the chain, and the genesis sentinel* — lives in an external
file (``ledger/data/ledger.yaml`` by default) rather than in code. That is a
deliberate design choice: the knobs can be reviewed and tuned without touching —
or redeploying — the builder. The loader validates aggressively (a non-empty
version, a hashlib-recognized algorithm, a non-empty blockchain version, and a
hex genesis sentinel) and fails with a typed
:class:`~device_ai.exceptions.LedgerConfigError` on any structural problem, so a
malformed file never silently degrades the ledger.

Keeping the builder's operational knobs in one immutable object (rather than
scattered literals) is what makes ledger construction reproducible and easy to
reason about.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from ..exceptions import LedgerConfigError

if TYPE_CHECKING:
    from ..configs.settings import Settings

#: Default ledger-config locator, relative to the ``device_ai`` package root.
DEFAULT_CONFIG_PATH = "ledger/data/ledger.yaml"

#: Default hash algorithm for computing block and record hashes.
DEFAULT_HASH_ALGORITHM = "sha256"

#: Default blockchain structure version stamped onto every produced chain.
DEFAULT_BLOCKCHAIN_VERSION = "1.0.0"

#: Genesis block sentinel: the 'previous_hash' value for the first block.
GENESIS_PREVIOUS_HASH = "0" * 64


@dataclass(frozen=True, slots=True)
class LedgerConfig:
    """Tunable configuration for the blockchain ledger core.

    Attributes:
        hash_algorithm: The cryptographic hash algorithm used for block and
            record integrity anchors. Must be a name recognized by Python's
            ``hashlib`` (e.g. ``sha256``, ``sha3_256``).
        blockchain_version: Semantic version stamped onto every produced
            :class:`~device_ai.ledger.models.Blockchain`.
        genesis_previous_hash: The sentinel value used as the ``previous_hash``
            for the genesis block (index ``0``). Defaults to 64 zero characters
            (the hex length of a SHA-256 digest).
        config_path: Locator of the external ledger-config file, resolved
            relative to the ``device_ai`` package root when not absolute.
    """

    hash_algorithm: str = DEFAULT_HASH_ALGORITHM
    blockchain_version: str = DEFAULT_BLOCKCHAIN_VERSION
    genesis_previous_hash: str = GENESIS_PREVIOUS_HASH
    config_path: str = DEFAULT_CONFIG_PATH

    def resolved_config_path(self, *, package_root: Path) -> Path:
        """Return the absolute ledger-config path.

        Relative :attr:`config_path` values are resolved against the given
        ``package_root`` (the ``device_ai`` package directory), so the packaged
        config is found regardless of the process working directory.

        Args:
            package_root: The ``device_ai`` package directory.

        Returns:
            The absolute path to the ledger-config file.
        """
        candidate = Path(self.config_path)
        if candidate.is_absolute():
            return candidate
        return package_root / candidate

    @classmethod
    def from_settings(cls, settings: Settings) -> LedgerConfig:
        """Build a config from application settings.

        The ledger has no env-driven knobs in M3.1 (its policy lives in the
        external YAML file), so this returns the default config. The method
        exists to mirror the trust/integrity/passport pattern and provide a hook
        for future env-driven configuration.

        Args:
            settings: The application :class:`~device_ai.configs.settings.Settings`.

        Returns:
            A :class:`LedgerConfig` with default values.
        """
        return cls()


def _require_mapping(value: Any, *, path: Path) -> dict[str, Any]:
    """Return ``value`` as a mapping or raise :class:`LedgerConfigError`."""
    if not isinstance(value, dict):
        raise LedgerConfigError(
            f"Ledger config root must be a mapping, got {type(value).__name__}.",
            details={"path": str(path)},
        )
    return value


def _require_str(value: Any, *, field: str, path: Path) -> str:
    """Return a non-empty string field or raise :class:`LedgerConfigError`."""
    if not isinstance(value, str) or not value.strip():
        raise LedgerConfigError(
            f"Ledger config needs a non-empty '{field}' string.",
            details={"path": str(path), "field": field},
        )
    return value.strip()


def _read_config(path: Path) -> dict[str, Any]:
    """Parse the config file (YAML or JSON) into a mapping.

    Raises:
        LedgerConfigError: If the file is missing, unparseable, or not a
            mapping.
    """
    if not path.exists():
        raise LedgerConfigError(
            f"Ledger config not found: {path}",
            details={"path": str(path)},
        )
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(text)
        else:
            raw = yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise LedgerConfigError(
            f"Failed to parse ledger config '{path}': {exc}",
            details={"path": str(path)},
        ) from exc
    if raw is None:
        raise LedgerConfigError(
            f"Ledger config is empty: {path}",
            details={"path": str(path)},
        )
    return _require_mapping(raw, path=path)


def load_config(path: str | Path) -> LedgerConfig:
    """Load and validate the external blockchain-ledger config.

    Reads the YAML (or JSON) config, validates the document version, the hash
    algorithm (non-empty and recognized by :func:`hashlib.new`), the blockchain
    version (non-empty) and the genesis sentinel (a non-empty hex string), and
    builds the immutable :class:`LedgerConfig`.

    Args:
        path: Path to the config file (``.yaml``/``.yml``/``.json``).

    Returns:
        The validated, immutable :class:`LedgerConfig`.

    Raises:
        LedgerConfigError: If the file is missing/malformed or fails validation.
    """
    config_path = Path(path)
    raw = _read_config(config_path)

    version = str(raw.get("version", "")).strip()
    if not version:
        raise LedgerConfigError(
            f"Ledger config '{config_path}' is missing a non-empty 'version'.",
            details={"path": str(config_path)},
        )

    hash_algorithm = _require_str(
        raw.get("hash_algorithm", DEFAULT_HASH_ALGORITHM),
        field="hash_algorithm",
        path=config_path,
    )
    if hash_algorithm not in hashlib.algorithms_available:
        raise LedgerConfigError(
            f"Ledger config '{config_path}' names unsupported hash algorithm "
            f"'{hash_algorithm}'.",
            details={"path": str(config_path), "hash_algorithm": hash_algorithm},
        )

    blockchain_version = _require_str(
        raw.get("blockchain_version", DEFAULT_BLOCKCHAIN_VERSION),
        field="blockchain_version",
        path=config_path,
    )

    genesis_previous_hash = _require_str(
        raw.get("genesis_previous_hash", GENESIS_PREVIOUS_HASH),
        field="genesis_previous_hash",
        path=config_path,
    )
    try:
        int(genesis_previous_hash, 16)
    except ValueError as exc:
        raise LedgerConfigError(
            f"Ledger config '{config_path}' genesis_previous_hash must be a hex "
            f"string, got '{genesis_previous_hash}'.",
            details={"path": str(config_path)},
        ) from exc

    return LedgerConfig(
        hash_algorithm=hash_algorithm,
        blockchain_version=blockchain_version,
        genesis_previous_hash=genesis_previous_hash,
        config_path=str(path),
    )
