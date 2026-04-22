from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Taxonomy Agent"
APP_DIR_NAME = "TaxonomyAgent"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resource_root() -> Path:
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return project_root()


def local_app_data_dir() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / ".local" / "share"
    out = root / APP_DIR_NAME
    out.mkdir(parents=True, exist_ok=True)
    return out


def user_data_path(*parts: str) -> Path:
    path = local_app_data_dir().joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
