from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from app.runtime_paths import user_data_path

PREFERENCES_PATH = user_data_path("preferences.json")
DEFAULT_PREFERENCES: Dict[str, Any] = {
    "export_mode": "ask",           # ask | fixed
    "export_directory": "",
    "teams_indexing_mode": "download",  # download | com
}


def _normalize(prefs: Dict[str, Any] | None) -> Dict[str, Any]:
    data = dict(DEFAULT_PREFERENCES)
    if prefs:
        data.update({k: v for k, v in prefs.items() if k in DEFAULT_PREFERENCES})
    mode = str(data.get("export_mode") or "ask").strip().lower()
    if mode not in {"ask", "fixed"}:
        mode = "ask"
    data["export_mode"] = mode
    data["export_directory"] = str(data.get("export_directory") or "").strip()
    teams_mode = str(data.get("teams_indexing_mode") or "download").strip().lower()
    if teams_mode not in {"download", "com"}:
        teams_mode = "download"
    data["teams_indexing_mode"] = teams_mode
    return data


def load_preferences() -> Dict[str, Any]:
    path = Path(PREFERENCES_PATH)
    if not path.exists():
        return dict(DEFAULT_PREFERENCES)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return dict(DEFAULT_PREFERENCES)
        return _normalize(raw)
    except Exception:
        return dict(DEFAULT_PREFERENCES)



def save_preferences(prefs: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize(prefs)
    path = Path(PREFERENCES_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    return normalized
