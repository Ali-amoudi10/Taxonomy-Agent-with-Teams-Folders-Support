from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from app.config_manager import apply_env, load_env_file, missing_required_keys, user_env_path
from app.runtime_paths import local_app_data_dir, project_root
from core.logging import get_logger, log_file_path

START_TIMEOUT_SECONDS = 45
HEALTH_PATH = "/health"

logger = get_logger("taxonomy_agent.launcher")


def _load_env() -> None:
    """Merge env files in priority order: template < project .env < user config.
    A later file only wins if its value is non-empty, so blank placeholder entries
    in lower-priority files never clear real values set by higher-priority files."""
    from dotenv import dotenv_values

    merged: dict[str, str] = {}
    for path in [
        project_root() / ".env.template",
        project_root() / ".env",
        local_app_data_dir() / ".env",
    ]:
        if not path.exists():
            continue
        for k, v in dotenv_values(path).items():
            if k is None:
                continue
            key, val = str(k), str(v) if v is not None else ""
            if val or key not in merged:
                merged[key] = val

    for key, value in merged.items():
        if value:
            os.environ[key] = value
        elif key not in os.environ:
            os.environ[key] = ""


def _ensure_configured(force: bool = False) -> bool:
    merged = {}
    template_path = project_root() / ".env.template"
    if template_path.exists():
        merged.update(load_env_file(template_path))
    project_env = project_root() / ".env"
    if project_env.exists():
        merged.update(load_env_file(project_env))
    merged.update(load_env_file(user_env_path()))
    needs_wizard = force or bool(missing_required_keys(merged))
    if not needs_wizard:
        apply_env(merged)
        logger.info("[CONFIG] using saved configuration from %s", user_env_path())
        return True

    from config_wizard import run_config_wizard

    logger.info("[CONFIG] launching configuration wizard")
    ok = run_config_wizard()
    if not ok:
        return False
    refreshed = {}
    if template_path.exists():
        refreshed.update(load_env_file(template_path))
    refreshed.update(load_env_file(user_env_path()))
    apply_env(refreshed)
    missing = missing_required_keys(refreshed)
    if missing:
        logger.error("[CONFIG] configuration is still incomplete: %s", missing)
        return False
    logger.info("[CONFIG] configuration saved to %s", user_env_path())
    return True


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _find_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def _wait_for_health(url: str, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 300:
                    return True
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.4)
    return False


def _serve(host: str, port: int) -> None:
    import uvicorn
    from app.ui.server import app

    logger.info("[SERVER] starting on %s:%s", host, port)
    uvicorn.run(app, host=host, port=port, reload=False, log_level="warning", access_log=False)


def main() -> None:
    logger.info("[APP] launch requested")
    logger.info("[APP] log file: %s", log_file_path())
    _load_env()

    args = {arg.strip().lower() for arg in sys.argv[1:]}
    force_config = "--configure" in args or "--configure-only" in args
    if not _ensure_configured(force=force_config):
        return
    if "--configure-only" in args:
        return

    from app.settings import load_settings

    settings = load_settings()
    host = settings.host
    port = settings.port

    if _is_port_open(host, port):
        logger.warning("[APP] configured port %s is busy; selecting a free port", port)
        port = _find_free_port(host)

    os.environ["APP_PORT"] = str(port)
    local_app_data_dir().mkdir(parents=True, exist_ok=True)

    thread = threading.Thread(target=_serve, args=(host, port), daemon=False, name="taxonomy-agent-server")
    thread.start()

    app_url = f"http://{host}:{port}"
    health_url = f"{app_url}{HEALTH_PATH}"
    if _wait_for_health(health_url, START_TIMEOUT_SECONDS):
        logger.info("[APP] server is healthy at %s", app_url)
        webbrowser.open(app_url, new=2)
    else:
        logger.error("[APP] server did not become healthy within %s seconds", START_TIMEOUT_SECONDS)

    thread.join()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("[APP] fatal launcher error")
        raise
