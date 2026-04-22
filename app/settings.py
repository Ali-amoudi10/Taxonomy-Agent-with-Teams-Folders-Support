from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from app.runtime_paths import user_data_path

load_dotenv()


def _get_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("APP_HOST", "127.0.0.1")
    port: int = _get_int("APP_PORT", 8765)
    scan_max_files: int = _get_int("SCAN_MAX_FILES", 1000)
    max_text_chars_per_file: int = _get_int("MAX_TEXT_CHARS_PER_FILE", 40000)
    text_cache_path: str = os.getenv("TEXT_CACHE_PATH", str(user_data_path("cache", "pptx_text_cache.json")))

    # Retrieval tuning
    search_candidate_k: int = _get_int("SEARCH_CANDIDATE_K", 200)
    search_max_results: int = _get_int("SEARCH_MAX_RESULTS", 100)
    search_min_score: float = _get_float("SEARCH_MIN_SCORE", 0.30)
    search_relative_margin: float = _get_float("SEARCH_RELATIVE_MARGIN", 0.1)
    search_max_per_deck: int = _get_int("SEARCH_MAX_PER_DECK", 1000)

    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_openai_api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    azure_openai_deployment: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.2-chat")

    memory_window_messages: int = _get_int("MEMORY_WINDOW_MESSAGES", 20)

    # SharePoint config retained for existing source support.
    sharepoint_tenant_id: str = os.getenv("SHAREPOINT_TENANT_ID", "")
    sharepoint_client_id: str = os.getenv("SHAREPOINT_CLIENT_ID", "")
    sharepoint_client_secret: str = os.getenv("SHAREPOINT_CLIENT_SECRET", "")
    sharepoint_graph_base_url: str = os.getenv("SHAREPOINT_GRAPH_BASE_URL", "https://graph.microsoft.com/v1.0")
    sharepoint_timeout_seconds: int = _get_int("SHAREPOINT_TIMEOUT_SECONDS", 60)
    sharepoint_verify_tls: bool = os.getenv("SHAREPOINT_VERIFY_TLS", "true").strip().lower() not in {"0", "false", "no"}


def load_settings() -> Settings:
    return Settings()
