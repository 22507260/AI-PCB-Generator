"""Tests for .env merge helper in src/utils/env_file.py."""

from __future__ import annotations

from src.utils.env_file import merge_env_values


def test_merge_env_values_preserves_unknown_and_comments():
    existing = (
        "# Existing comment\n"
        "OPENAI_MODEL=old-model\n"
        "CUSTOM_TOKEN=abc123\n"
        "\n"
    )
    updates = {
        "OPENAI_MODEL": "new-model",
        "OPENAI_MAX_TOKENS": "8192",
    }
    merged = merge_env_values(existing, updates, ordered_keys=["OPENAI_MODEL", "OPENAI_MAX_TOKENS"])

    assert "# Existing comment" in merged
    assert "CUSTOM_TOKEN=abc123" in merged
    assert "OPENAI_MODEL=new-model" in merged
    assert "OPENAI_MAX_TOKENS=8192" in merged


def test_merge_env_values_removes_key_when_none():
    existing = "OPENAI_API_KEY=secret\nOPENAI_MODEL=gpt-4o\n"
    updates = {
        "OPENAI_API_KEY": None,
        "OPENAI_MODEL": "gpt-4o-mini",
    }
    merged = merge_env_values(existing, updates)

    assert "OPENAI_API_KEY=" not in merged
    assert "OPENAI_MODEL=gpt-4o-mini" in merged


def test_merge_env_values_appends_missing_keys_in_order():
    existing = "CUSTOM=1\n"
    updates = {
        "B_KEY": "b",
        "A_KEY": "a",
    }
    merged = merge_env_values(existing, updates, ordered_keys=["A_KEY", "B_KEY"])
    lines = [line for line in merged.splitlines() if line]

    assert lines == ["CUSTOM=1", "A_KEY=a", "B_KEY=b"]
