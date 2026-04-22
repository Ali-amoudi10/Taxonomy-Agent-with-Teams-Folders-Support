from __future__ import annotations

from typing import Any, Dict, List, Optional
import os

# If you vendored your standalone package into the app, adjust imports accordingly:
# from app.rag_kb.config import KBConfig
# from app.rag_kb.retriever import search_slides

from app.rag_kb.config import KBConfig
from app.rag_kb.retriever import search_slides


def semantic_slide_search(
    query: str,
    top_k: int,
    source_root: str | None = None,
) -> List[Dict[str, Any]]:
    cfg = KBConfig()
    return search_slides(query=query, cfg=cfg, top_k=top_k, source_root=source_root)