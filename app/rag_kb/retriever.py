from __future__ import annotations

from typing import Any, Dict, List

from app.rag_kb.chroma_store import ChromaSlideStore
from app.rag_kb.config import KBConfig


def search_slides(
    query: str,
    cfg: KBConfig,
    top_k: int = 30,
    source_root: str | None = None,
) -> List[Dict[str, Any]]:
    store = ChromaSlideStore(cfg)
    res = store.query(query_text=query, k=top_k, source_root=source_root)

    ids = (res.get("ids") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    out: List[Dict[str, Any]] = []
    for slide_id, doc, meta, dist in zip(ids, docs, metas, dists):
        score = float(1.0 - dist) if dist is not None else 0.0
        meta = dict(meta or {})
        snippet = doc
        if isinstance(snippet, str) and len(snippet) > 350:
            snippet = snippet[:350] + "…"
        out.append(
            {
                "id": slide_id,
                "score": score,
                "path": meta.get("pptx_path"),
                "source_root": meta.get("source_root"),
                "deck_title": meta.get("deck_title"),
                "slide_number": meta.get("slide_number"),
                "num_slides": meta.get("num_slides"),
                "doc_hash": meta.get("doc_hash"),
                "snippet": snippet,
            }
        )

    out.sort(key=lambda item: item["score"], reverse=True)
    return out
