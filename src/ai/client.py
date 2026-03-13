"""OpenAI API client wrapper for circuit generation."""

from __future__ import annotations

import json
from typing import AsyncIterator

from openai import OpenAI
from pydantic import ValidationError

from src.ai.prompts import build_messages
from src.ai.schemas import CircuitSpec
from src.config import get_settings
from src.utils.logger import get_logger

log = get_logger("ai.client")


class AIClientError(Exception):
    """Raised when the AI client encounters an unrecoverable error."""


class AIClient:
    """Synchronous OpenAI wrapper that returns validated CircuitSpec objects."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        settings = get_settings()
        self._api_key = api_key or settings.openai_api_key
        self._model = model or settings.openai_model
        self._max_tokens = settings.openai_max_tokens
        self._temperature = settings.openai_temperature

        if not self._api_key:
            raise AIClientError(
                "OpenAI API key is not configured. "
                "Set OPENAI_API_KEY in your .env file or application settings."
            )

        base_url = settings.openai_base_url.strip() or None
        self._client = OpenAI(api_key=self._api_key, base_url=base_url)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_circuit(self, description: str) -> CircuitSpec:
        """Send a natural-language description and return a validated CircuitSpec.

        Raises AIClientError on API or validation failures.
        """
        if not description or not description.strip():
            raise AIClientError("Circuit description cannot be empty.")

        messages = build_messages(description.strip())
        log.info("Generating circuit for: %s", description[:120])

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            log.error("OpenAI API error: %s", exc)
            raise AIClientError(f"OpenAI API request failed: {exc}") from exc

        raw = response.choices[0].message.content
        if not raw:
            raise AIClientError("AI returned an empty response.")

        log.debug("Raw AI response length: %d chars", len(raw))
        return self._parse_response(raw)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _parse_response(self, raw: str) -> CircuitSpec:
        """Parse raw JSON string into a validated CircuitSpec."""
        # Strip potential markdown fences
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            # Remove first and last ``` lines
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            log.error("Failed to parse AI JSON: %s", exc)
            raise AIClientError(f"AI response is not valid JSON: {exc}") from exc

        try:
            spec = CircuitSpec.model_validate(data)
        except ValidationError as exc:
            log.error("Circuit spec validation failed: %s", exc)
            raise AIClientError(
                f"AI response does not match expected schema:\n{exc}"
            ) from exc

        log.info(
            "Circuit parsed: %s — %d components, %d nets",
            spec.name,
            spec.component_count,
            spec.net_count,
        )
        return spec
