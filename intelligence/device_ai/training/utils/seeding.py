"""Deterministic seeding for reproducible training runs.

:func:`seed_everything` seeds Python's :mod:`random`, NumPy and — only when it
is already installed — PyTorch (CPU and CUDA). Torch is imported behind a guard
so the base environment, which ships neither torch nor any real trainer, seeds
just the always-present sources without error.
"""

from __future__ import annotations

import random

import numpy as np


def seed_everything(seed: int, *, deterministic: bool = True) -> int:
    """Seed all available RNGs for a reproducible run.

    Seeds :mod:`random` and :mod:`numpy` unconditionally, and PyTorch (plus its
    CUDA generators and deterministic cuDNN flags) when torch is importable.

    Args:
        seed: Non-negative seed value shared across every RNG.
        deterministic: When ``True`` and torch is present, request deterministic
            cuDNN behaviour (reproducible at a small performance cost).

    Returns:
        The ``seed`` that was applied (echoed for convenient logging/records).

    Raises:
        ValueError: If ``seed`` is negative.
    """
    if seed < 0:
        raise ValueError(f"seed must be non-negative, got {seed}")

    random.seed(seed)
    np.random.seed(seed)
    _seed_torch(seed, deterministic=deterministic)
    return seed


def _seed_torch(seed: int, *, deterministic: bool) -> None:
    """Seed PyTorch if it is installed; a no-op otherwise.

    Args:
        seed: The seed to apply to torch's CPU and CUDA generators.
        deterministic: Whether to force deterministic cuDNN behaviour.
    """
    try:  # pragma: no cover - torch is not installed in the base environment
        import torch
    except ImportError:
        return

    torch.manual_seed(seed)  # pragma: no cover
    if torch.cuda.is_available():  # pragma: no cover
        torch.cuda.manual_seed_all(seed)
    if deterministic:  # pragma: no cover
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
