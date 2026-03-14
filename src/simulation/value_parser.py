"""Parse component value strings like '10kΩ', '100nF', '4.7µF' into floats."""

from __future__ import annotations

import re

# SI prefix multipliers
_SI_PREFIX: dict[str, float] = {
    "f": 1e-15,
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,
    "μ": 1e-6,  # Greek mu
    "m": 1e-3,
    "k": 1e3,
    "K": 1e3,
    "meg": 1e6,
    "M": 1e6,
    "g": 1e9,
    "G": 1e9,
    "t": 1e12,
    "T": 1e12,
}

# Unit suffixes to strip (case-insensitive matching handled separately)
_UNIT_SUFFIXES = ("Ω", "ohm", "ohms", "F", "H", "V", "A", "Hz", "hz", "w", "W")

# Pattern: optional number, optional SI prefix, optional unit
_VALUE_RE = re.compile(
    r"^\s*"
    r"([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"  # numeric part
    r"\s*"
    r"(meg|[fpnuµμmkKMgGtT])?"                # SI prefix
    r"\s*"
    r"(\S*)"                                    # optional unit suffix
    r"\s*$"
)

# Alternate pattern: number with prefix embedded (e.g., "4k7" → 4700)
_EMBEDDED_RE = re.compile(
    r"^\s*"
    r"(\d+)"                                    # integer part
    r"(meg|[fpnuµμmkKMgGtT])"                  # SI prefix
    r"(\d+)"                                    # fractional part
    r"\s*(\S*)\s*$"
)


def parse_value(text: str) -> float:
    """Convert a component value string to a float.

    Examples:
        >>> parse_value("10kΩ")
        10000.0
        >>> parse_value("100nF")
        1e-07
        >>> parse_value("4.7µF")
        4.7e-06
        >>> parse_value("4k7")
        4700.0
        >>> parse_value("1M")
        1000000.0
        >>> parse_value("0.1")
        0.1
    """
    if not text or not text.strip():
        return 0.0

    cleaned = text.strip()

    # Try embedded format first: "4k7" → 4.7k
    m = _EMBEDDED_RE.match(cleaned)
    if m:
        integer, prefix, frac, _ = m.groups()
        numeric = float(f"{integer}.{frac}")
        multiplier = _SI_PREFIX.get(prefix, 1.0)
        return numeric * multiplier

    # Standard format: "10kΩ", "100n", "4.7µF"
    m = _VALUE_RE.match(cleaned)
    if m:
        num_str, prefix, _ = m.groups()
        numeric = float(num_str)
        multiplier = _SI_PREFIX.get(prefix, 1.0) if prefix else 1.0
        return numeric * multiplier

    # Last resort: try to extract any leading number
    m = re.match(r"([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", cleaned)
    if m:
        return float(m.group(1))

    return 0.0
