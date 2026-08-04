"""Filesystem helpers.

Small, dependency-free utilities for working with paths and file
extensions. Kept separate from image logic so they can be reused by the
future training/evaluation code without pulling in imaging libraries.
"""

from __future__ import annotations

from pathlib import Path


def ensure_directory(path: Path) -> Path:
    """Create ``path`` (and parents) if missing and return it.

    Args:
        path: Directory to create.

    Returns:
        The same path, now guaranteed to exist.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_extension(filename: str | None) -> str:
    """Return the lower-cased file extension including the leading dot.

    Args:
        filename: A file name or path; ``None`` is treated as empty.

    Returns:
        The extension (e.g. ``".jpg"``) or an empty string if absent.
    """
    if not filename:
        return ""
    return Path(filename).suffix.lower()


def sanitize_filename(filename: str | None, *, fallback: str = "upload") -> str:
    """Return a safe basename stripped of any directory components.

    Prevents path-traversal by discarding directory separators supplied by
    the client and keeping only the final path component.

    Args:
        filename: Client-supplied file name (untrusted).
        fallback: Name to use when the input is empty after sanitising.

    Returns:
        A safe file name with no directory components.
    """
    if not filename:
        return fallback
    # ``Path().name`` drops any parent components on both POSIX and Windows.
    safe = Path(filename.replace("\\", "/")).name.strip()
    return safe or fallback
