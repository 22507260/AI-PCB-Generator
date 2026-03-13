"""Input validators."""

from __future__ import annotations


def sanitize_description(text: str) -> str:
    """Clean up user circuit description before sending to AI."""
    text = text.strip()
    # Collapse multiple whitespace
    import re
    text = re.sub(r"\s+", " ", text)
    return text
