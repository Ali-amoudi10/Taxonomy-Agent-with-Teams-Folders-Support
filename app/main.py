from __future__ import annotations

import os

import uvicorn

from app.settings import load_settings


def main() -> None:
    s = load_settings()
    reload_enabled = os.getenv("APP_RELOAD", "false").strip().lower() in {"1", "true", "yes"}
    uvicorn.run("app.ui.server:app", host=s.host, port=s.port, reload=reload_enabled)

if __name__ == "__main__":
    main()