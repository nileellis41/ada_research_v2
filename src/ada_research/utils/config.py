"""Centralized configuration backed by environment variables.

Each consumer asks `Config.has_fred_key()` etc. and degrades gracefully
when a key is missing. The app never crashes for a missing key; tabs
just show a configuration prompt instead of their content.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root, regardless of where the app is launched from.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Config:
    """Read-only snapshot of environment configuration."""

    fred_api_key: str | None = os.getenv("FRED_API_KEY") or None
    fmp_api_key: str | None = os.getenv("FMP_API_KEY") or None
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    outputs_dir: Path = Path(os.getenv("OUTPUTS_DIR", _PROJECT_ROOT / "outputs"))
    project_root: Path = _PROJECT_ROOT

    def has_fred_key(self) -> bool:
        return bool(self.fred_api_key and self.fred_api_key.strip())

    def has_fmp_key(self) -> bool:
        return bool(self.fmp_api_key and self.fmp_api_key.strip())

    def has_anthropic_key(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.strip())


# Single shared instance — import this everywhere
config = Config()
