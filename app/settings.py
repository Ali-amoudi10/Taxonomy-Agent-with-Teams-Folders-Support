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
    # ── Server ────────────────────────────────────────────────────────────────

    # Bind address for the local web server. Use "0.0.0.0" to expose on the LAN.
    host: str = os.getenv("APP_HOST", "127.0.0.1")

    # TCP port the web server listens on.
    port: int = _get_int("APP_PORT", 8765)

    # ── Indexing ──────────────────────────────────────────────────────────────

    # Hard cap on PPTX files examined per directory scan. Prevents runaway scans
    # on very large network shares. Raise if your library exceeds this limit.
    scan_max_files: int = _get_int("SCAN_MAX_FILES", 20000)

    # Maximum characters extracted from a single file. Larger values capture more
    # slide text but increase embedding cost and memory usage.
    max_text_chars_per_file: int = _get_int("MAX_TEXT_CHARS_PER_FILE", 40000)

    # Path for the slide-text extraction cache. Defaults to the user data directory
    # so the cache survives application updates without reconfiguration.
    text_cache_path: str = os.getenv(
        "TEXT_CACHE_PATH",
        str(user_data_path("cache", "pptx_text_cache.json")),
    )

    # ── Retrieval ─────────────────────────────────────────────────────────────

    # Number of candidate vectors fetched from Chroma before post-filtering.
    # Higher values improve recall at the cost of latency. 200 is a good default;
    # lower (e.g. 50) if searches feel slow, raise (e.g. 500) if results are sparse.
    search_candidate_k: int = _get_int("SEARCH_CANDIDATE_K", 200)

    # Maximum slides returned to the UI after all filters are applied.
    search_max_results: int = _get_int("SEARCH_MAX_RESULTS", 100)

    # Minimum cosine similarity required to include a slide. Range: 0.0–1.0.
    # Lower values broaden recall (more results, some off-topic).
    # Raise (e.g. 0.35) if results consistently feel irrelevant.
    search_min_score: float = _get_float("SEARCH_MIN_SCORE", 0.15)

    # Only include slides within this score delta of the best-matching slide.
    # 1.0 disables this filter entirely, relying solely on search_min_score.
    # Lower values (e.g. 0.15) narrow results to the very closest matches.
    search_relative_margin: float = _get_float("SEARCH_RELATIVE_MARGIN", 1.0)

    # Maximum slides included from any single presentation. Prevents one large
    # deck from dominating results when searching across many files.
    search_max_per_deck: int = _get_int("SEARCH_MAX_PER_DECK", 1000)

    # ── Display ───────────────────────────────────────────────────────────────

    # Cosine similarity that maps to 99 % in the match-percentage display.
    # Calibrate this to the ceiling you observe in [SCORE_RANGE] log lines after
    # a few real queries. Lower = higher displayed percentages for the same score.
    # Typical range: 0.40–0.65 depending on your content corpus.
    score_display_max: float = _get_float("SCORE_DISPLAY_MAX", 0.50)

    # ── Azure OpenAI — chat model ─────────────────────────────────────────────

    # Full REST endpoint URL for the Azure chat deployment. Required. Set in .env.
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")

    # Azure OpenAI API key. Required. Set in .env — never commit this value.
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")

    # Azure REST API version string for the chat deployment.
    azure_openai_api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")

    # Deployment name (model alias) configured in your Azure resource.
    azure_openai_deployment: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-nano")

    # ── Conversation memory ───────────────────────────────────────────────────

    # Number of past messages kept in the LLM context window per session.
    # Increase for longer conversational memory; decrease to reduce token cost.
    memory_window_messages: int = _get_int("MEMORY_WINDOW_MESSAGES", 20)

    # ── SharePoint / Microsoft Teams ──────────────────────────────────────────

    # Azure AD tenant ID for the Microsoft 365 app registration. Set in .env.
    sharepoint_tenant_id: str = os.getenv("SHAREPOINT_TENANT_ID", "")

    # Application (client) ID for the Microsoft 365 app registration. Set in .env.
    sharepoint_client_id: str = os.getenv("SHAREPOINT_CLIENT_ID", "")

    # Client secret for the app registration. Set in .env — never commit this value.
    sharepoint_client_secret: str = os.getenv("SHAREPOINT_CLIENT_SECRET", "")

    # Microsoft Graph API base URL. Only change if targeting a sovereign cloud
    # (e.g. GCC High: https://graph.microsoft.us/v1.0).
    sharepoint_graph_base_url: str = os.getenv(
        "SHAREPOINT_GRAPH_BASE_URL", "https://graph.microsoft.com/v1.0"
    )

    # HTTP timeout in seconds for Microsoft Graph API requests.
    sharepoint_timeout_seconds: int = _get_int("SHAREPOINT_TIMEOUT_SECONDS", 60)

    # Set to false only in test environments. Disabling TLS verification is insecure.
    sharepoint_verify_tls: bool = (
        os.getenv("SHAREPOINT_VERIFY_TLS", "true").strip().lower()
        not in {"0", "false", "no"}
    )


def load_settings() -> Settings:
    return Settings()
