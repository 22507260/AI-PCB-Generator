"""Application configuration using pydantic-settings and .env files."""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import Field


class AppSettings(BaseSettings):
    """Central application configuration.

    Values are loaded from environment variables and .env file.
    """

    # --- OpenAI ---
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_base_url: str = Field(default="", description="Custom API base URL (OpenAI-compatible)")
    openai_model: str = Field(default="gpt-4o", description="OpenAI model name")
    openai_max_tokens: int = Field(default=8192, description="Max tokens per response")
    openai_temperature: float = Field(default=0.2, description="Sampling temperature")

    # --- Paths ---
    kicad_path: str = Field(default="", description="KiCad installation directory")
    kicad_3dmodels_path: str = Field(default="", description="KiCad 3D models directory (auto-detected if empty)")
    freerouting_jar: str = Field(default="", description="Path to freerouting.jar")

    # --- PCB Defaults ---
    default_trace_width_mm: float = Field(default=0.25)
    default_clearance_mm: float = Field(default=0.2)
    default_via_diameter_mm: float = Field(default=0.8)
    default_via_drill_mm: float = Field(default=0.4)
    default_board_width_mm: float = Field(default=100.0)
    default_board_height_mm: float = Field(default=100.0)
    default_layers: int = Field(default=2, description="Number of copper layers (2, 4, 6)")

    # --- Logging ---
    log_level: str = Field(default="INFO")
    log_file: str = Field(default="logs/ai_pcb.log")

    # --- UI ---
    language: str = Field(default="tr", description="UI language: tr or en")
    theme: str = Field(default="dark", description="UI theme: dark or light")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# --- Derived paths ---

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
ASSETS_DIR = ROOT_DIR / "assets"
TEMPLATES_DIR = DATA_DIR / "templates"
LOGS_DIR = ROOT_DIR / "logs"


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached singleton settings instance."""
    # Ensure .env is loaded from project root
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        os.environ.setdefault("ENV_FILE", str(env_path))
    return AppSettings(_env_file=str(env_path) if env_path.exists() else None)
