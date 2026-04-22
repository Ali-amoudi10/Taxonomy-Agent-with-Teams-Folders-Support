from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

from app.runtime_paths import local_app_data_dir, resource_root

USER_ENV_NAME = ".env"
TEMPLATE_ENV_NAME = ".env.template"


def user_env_path() -> Path:
    return local_app_data_dir() / USER_ENV_NAME


def template_env_path() -> Path:
    return resource_root() / TEMPLATE_ENV_NAME


def load_env_file(path: Path | None = None) -> dict[str, str]:
    target = path or user_env_path()
    if not target.exists():
        return {}
    raw = dotenv_values(target)
    return {str(k): str(v) for k, v in raw.items() if k is not None and v is not None}


def merged_config() -> dict[str, str]:
    data = load_env_file(template_env_path())
    data.update(load_env_file(user_env_path()))
    return data


def _quote_env_value(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def write_env_file(values: dict[str, str], path: Path | None = None) -> Path:
    target = path or user_env_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={_quote_env_value(value or '')}" for key, value in values.items()]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def apply_env(values: dict[str, str], override: bool = True) -> None:
    for key, value in values.items():
        if not value and os.environ.get(key):
            # Never overwrite a real value with an empty string from a lower-priority config.
            continue
        if override or key not in os.environ:
            os.environ[key] = value


def required_keys_for(values: dict[str, str]) -> list[str]:
    provider = (values.get("LLM_PROVIDER") or "azure").strip().lower()
    if provider == "azure":
        return [
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_DEPLOYMENT",
            "AZURE_OPENAI_API_VERSION",
            "AZURE_OPENAI_EMBEDDING_ENDPOINT",
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
            "AZURE_OPENAI_EMBEDDING_API_VERSION",
        ]
    if provider == "openai":
        return ["OPENAI_API_KEY", "OPENAI_MODEL"]
    if provider == "hf_openai_compat":
        return ["HUGGINGFACEHUB_API_TOKEN", "HF_OPENAI_BASE_URL", "HF_MODEL_ID"]
    return []


def missing_required_keys(values: dict[str, str]) -> list[str]:
    return [key for key in required_keys_for(values) if not (values.get(key) or "").strip()]


def has_valid_user_config() -> bool:
    path = user_env_path()
    if not path.exists():
        return False
    vals = merged_config()
    return not missing_required_keys(vals)
