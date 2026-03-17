"""Helpers for reading/updating .env-like key-value files."""

from __future__ import annotations

from collections.abc import Iterable


def merge_env_values(
    existing_text: str,
    updates: dict[str, str | None],
    ordered_keys: Iterable[str] | None = None,
) -> str:
    """Merge key updates into an existing .env text while preserving unrelated lines.

    Behavior:
    - Preserves comments/blank lines and unknown keys as-is.
    - Replaces existing managed keys with updated values.
    - Removes existing managed keys when update value is None.
    - Appends missing managed keys at the end using ordered_keys.
    """
    managed_keys = set(updates.keys())
    output_lines: list[str] = []
    seen_managed: set[str] = set()

    for line in existing_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output_lines.append(line)
            continue

        key = stripped.split("=", 1)[0].strip()
        if key not in managed_keys:
            output_lines.append(line)
            continue

        seen_managed.add(key)
        value = updates.get(key)
        if value is not None:
            output_lines.append(f"{key}={value}")

    key_order = list(ordered_keys) if ordered_keys is not None else list(updates.keys())
    for key in key_order:
        if key in seen_managed:
            continue
        value = updates.get(key)
        if value is not None:
            output_lines.append(f"{key}={value}")
            seen_managed.add(key)

    # Any remaining managed keys not included in ordered_keys.
    for key, value in updates.items():
        if key not in seen_managed and value is not None:
            output_lines.append(f"{key}={value}")
            seen_managed.add(key)

    merged = "\n".join(output_lines).rstrip()
    return f"{merged}\n" if merged else ""
