"""Pattern matching and normalization for OCR identity extraction (M1.6).

Pure, dependency-free functions (regex + small validators) that turn a piece of
recognized text into candidate identity values, each carrying a
**pattern-strength weight** in ``[0, 1]``. The parser combines that weight with
the backend's recognition confidence to score a field.

Everything here is deterministic and side-effect free, so the whole extraction
layer is unit-testable from hand-built strings — no images, no OCR backend.

Design notes:

* **Confusion normalization is opt-in per candidate**, applied *only* to
  structured-ID candidates (serial/IMEI/MAC) before validation — never to free
  text like a manufacturer name, where ``O``→``0`` would corrupt the value.
* **IMEI** is validated with the **Luhn** checksum (a Luhn pass is strong
  evidence); **MAC** and **IMEI** shapes are matched with anchored regexes.
* The **manufacturer** table is a small, case-insensitive keyword set; matching
  is exact-token to avoid false positives inside longer words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Candidate value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PatternCandidate:
    """A candidate identity value produced by a matcher.

    Attributes:
        value: The normalized candidate value.
        strength: Pattern-strength weight in ``[0, 1]`` — how strongly the
            text matches the expected shape (e.g. a Luhn-valid IMEI scores
            higher than a bare 15-digit run).
        raw_text: The original text the candidate was derived from.
    """

    value: str
    strength: float
    raw_text: str


# ---------------------------------------------------------------------------
# OCR-confusion normalization (structured IDs only)
# ---------------------------------------------------------------------------

#: Common OCR misreads for *digit-dominant* identifiers. Applied only to
#: structured-ID candidates before validation, never to free text.
_DIGIT_CONFUSIONS = {"O": "0", "o": "0", "I": "1", "l": "1", "S": "5", "B": "8"}


def normalize_confusions(text: str) -> str:
    """Map common OCR character confusions to their digit forms.

    Intended for **structured identifiers** (serial/IMEI/MAC) where the
    alphabet is digit-dominant, so ``O``/``I``/``S``/``B`` are far more likely
    to be misread digits than letters. Never apply this to free text.

    Args:
        text: The raw candidate text.

    Returns:
        The text with confusable characters mapped to digits.
    """
    return "".join(_DIGIT_CONFUSIONS.get(char, char) for char in text)


# ---------------------------------------------------------------------------
# Label detection
# ---------------------------------------------------------------------------

#: Label keywords that, when they prefix/precede a token, boost the field the
#: token is parsed as. Maps a lower-cased label fragment to a field kind.
_SERIAL_LABELS = ("serial", "s/n", "sn", "ser no", "serial no", "serial number")
_MODEL_LABELS = ("model", "model no", "model number", "type", "m/n")
_IMEI_LABELS = ("imei", "imei1", "imei2", "meid")
_MAC_LABELS = ("mac", "mac address", "wlan mac", "eth mac", "wifi mac")


def _has_label(text: str, labels: tuple[str, ...]) -> bool:
    """Return whether ``text`` contains any of ``labels`` (case-insensitive)."""
    lowered = text.lower()
    return any(label in lowered for label in labels)


def has_serial_label(text: str) -> bool:
    """Whether ``text`` carries a serial-number label."""
    return _has_label(text, _SERIAL_LABELS)


def has_model_label(text: str) -> bool:
    """Whether ``text`` carries a model label."""
    return _has_label(text, _MODEL_LABELS)


def has_imei_label(text: str) -> bool:
    """Whether ``text`` carries an IMEI label."""
    return _has_label(text, _IMEI_LABELS)


def has_mac_label(text: str) -> bool:
    """Whether ``text`` carries a MAC-address label."""
    return _has_label(text, _MAC_LABELS)


def strip_label(text: str) -> str:
    """Return the value portion of a ``label: value`` span.

    Splits on the first ``:`` or ``=`` when present, else returns the whole
    text trimmed. Used to isolate the token following a recognized label.

    Args:
        text: The raw span text (possibly ``"S/N: ABC123"``).

    Returns:
        The trimmed value portion.
    """
    for separator in (":", "="):
        if separator in text:
            return text.split(separator, 1)[1].strip()
    return text.strip()


# ---------------------------------------------------------------------------
# IMEI (15 digits, validated by Luhn)
# ---------------------------------------------------------------------------

#: Fifteen consecutive digits, optionally separated by spaces/hyphens.
_IMEI_RE = re.compile(r"(?<!\d)(\d[\d\s-]{13,20}\d)(?!\d)")


def luhn_valid(digits: str) -> bool:
    """Return whether ``digits`` passes the Luhn checksum.

    Args:
        digits: A string of decimal digits.

    Returns:
        ``True`` when the Luhn check digit is consistent, else ``False``.
        A non-digit or empty string is never valid.
    """
    if not digits or not digits.isdigit():
        return False
    total = 0
    # Double every second digit from the right.
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def find_imei(text: str) -> PatternCandidate | None:
    """Return an IMEI candidate from ``text``, or ``None`` when none matches.

    The digit run is confusion-normalized first (letters that are almost
    certainly misread digits), then required to be exactly 15 digits. A
    Luhn-valid IMEI is strong (``0.98``); a well-shaped but Luhn-failing run is
    weak (``0.55``) so a labelled-but-imperfect read can still surface.

    Args:
        text: The raw span text.

    Returns:
        The best IMEI :class:`PatternCandidate`, or ``None``.
    """
    normalized = normalize_confusions(text)
    match = _IMEI_RE.search(normalized)
    if match is None:
        return None
    digits = re.sub(r"[\s-]", "", match.group(1))
    if len(digits) != 15:
        return None
    strength = 0.98 if luhn_valid(digits) else 0.55
    return PatternCandidate(value=digits, strength=strength, raw_text=text)


# ---------------------------------------------------------------------------
# MAC address
# ---------------------------------------------------------------------------

#: Six hex octets separated by ``:`` or ``-``.
_MAC_RE = re.compile(
    r"(?<![0-9A-Fa-f])([0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5})(?![0-9A-Fa-f])"
)


def find_mac(text: str) -> PatternCandidate | None:
    """Return a MAC-address candidate from ``text``, or ``None``.

    The canonical value is upper-cased and colon-separated. A well-formed MAC
    is unambiguous, so the pattern strength is high (``0.97``).

    Args:
        text: The raw span text.

    Returns:
        The MAC :class:`PatternCandidate`, or ``None``.
    """
    match = _MAC_RE.search(text)
    if match is None:
        return None
    octets = re.split(r"[:-]", match.group(1))
    value = ":".join(octet.upper() for octet in octets)
    return PatternCandidate(value=value, strength=0.97, raw_text=text)


# ---------------------------------------------------------------------------
# Serial number (heuristic)
# ---------------------------------------------------------------------------

#: An alphanumeric token (optionally with internal hyphens) of plausible
#: serial length. Anchored so surrounding punctuation is excluded.
_SERIAL_TOKEN_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9-]{4,24}[A-Za-z0-9])")


def find_serial(text: str, *, labelled: bool = False) -> PatternCandidate | None:
    """Return a serial-number candidate from ``text``, or ``None``.

    A serial is a mixed alphanumeric token of moderate length. Because that
    shape also matches ordinary words, an unlabelled candidate must contain at
    least one digit *and* one letter (a strong serial signal); a labelled span
    (``"S/N: ..."``) relaxes this and scores higher.

    Args:
        text: The raw span text (the value portion, label already stripped by
            the caller when ``labelled`` is True).
        labelled: Whether a serial label preceded this value.

    Returns:
        The serial :class:`PatternCandidate`, or ``None``.
    """
    match = _SERIAL_TOKEN_RE.search(text.strip())
    if match is None:
        return None
    token = match.group(1)
    has_digit = any(char.isdigit() for char in token)
    has_alpha = any(char.isalpha() for char in token)
    mixed = has_digit and has_alpha
    if not labelled and not mixed:
        return None
    # Labelled + mixed is the strongest signal; label alone or mixed alone is
    # moderate. Confusion normalization is deliberately NOT applied: serials
    # legitimately contain letters.
    if labelled and mixed:
        strength = 0.9
    elif labelled or mixed:
        strength = 0.7
    else:  # pragma: no cover - unreachable (guarded above), kept for clarity
        strength = 0.4
    return PatternCandidate(value=token.upper(), strength=strength, raw_text=text)


# ---------------------------------------------------------------------------
# Manufacturer (keyword table)
# ---------------------------------------------------------------------------

#: Canonical manufacturer names keyed by their lower-cased match token. New
#: brands are added here in one place.
_MANUFACTURERS = {
    "dell": "Dell",
    "hp": "HP",
    "hewlett-packard": "HP",
    "hewlett packard": "HP",
    "apple": "Apple",
    "samsung": "Samsung",
    "lenovo": "Lenovo",
    "asus": "Asus",
    "acer": "Acer",
    "microsoft": "Microsoft",
    "sony": "Sony",
    "lg": "LG",
    "toshiba": "Toshiba",
    "google": "Google",
    "xiaomi": "Xiaomi",
    "huawei": "Huawei",
    "nokia": "Nokia",
    "motorola": "Motorola",
    "oneplus": "OnePlus",
}


# ---------------------------------------------------------------------------
# Model (label-driven; no intrinsic shape)
# ---------------------------------------------------------------------------

#: A model designator has no reliable intrinsic shape (``"XPS 15"``,
#: ``"iPhone 13"``, ``"ViT-B-32"``), so it is only extracted from a labelled
#: span. This just bounds a plausible value.
_MODEL_VALUE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ./-]{1,38}[A-Za-z0-9]")


def find_model(text: str, *, labelled: bool = False) -> PatternCandidate | None:
    """Return a model candidate from ``text``, or ``None``.

    Because a model has no reliable intrinsic shape, extraction relies on a
    preceding label; an unlabelled span never yields a model candidate. The
    value is whitespace-collapsed and length-bounded.

    Args:
        text: The value text (label already stripped by the caller).
        labelled: Whether a model label preceded this value. Required to be
            ``True`` for a candidate to be returned.

    Returns:
        The model :class:`PatternCandidate`, or ``None``.
    """
    if not labelled:
        return None
    collapsed = " ".join(text.split())
    match = _MODEL_VALUE_RE.match(collapsed)
    if match is None:
        return None
    return PatternCandidate(value=match.group(0), strength=0.85, raw_text=text)


def find_manufacturer(text: str) -> PatternCandidate | None:
    """Return a manufacturer candidate from ``text``, or ``None``.

    Matching is case-insensitive and token-based (word boundaries), so
    ``"Dell Inc."`` matches ``Dell`` but ``"Delaware"`` does not. A keyword hit
    is unambiguous, hence a high strength (``0.95``).

    Args:
        text: The raw span text.

    Returns:
        The manufacturer :class:`PatternCandidate`, or ``None``.
    """
    lowered = text.lower()
    for token, canonical in _MANUFACTURERS.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lowered):
            return PatternCandidate(value=canonical, strength=0.95, raw_text=text)
    return None


def known_manufacturers() -> tuple[str, ...]:
    """Return the sorted set of canonical manufacturer names (for docs/tests)."""
    return tuple(sorted(set(_MANUFACTURERS.values())))
