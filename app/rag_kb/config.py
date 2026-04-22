from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

from app.runtime_paths import user_data_path

load_dotenv()

@dataclass(frozen=True)
class KBConfig:
    chroma_dir: str = os.getenv("CHROMA_DIR", str(user_data_path("chroma_data")))
    collection: str = os.getenv("CHROMA_COLLECTION", "pptx_slides")
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_openai_embed_model: str = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
    azure_openai_api_version: str = os.getenv("AZURE_OPENAI_EMBEDDING_API_VERSION", "2023-05-15")
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT", "")