from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import AzureOpenAI

from app.rag_kb.config import KBConfig


class ChromaSlideStore:
    def __init__(self, cfg: KBConfig):
        self.cfg = cfg
        self.client = chromadb.PersistentClient(
            path=cfg.chroma_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=cfg.collection,
            metadata={"hnsw:space": "cosine"},
        )
        self.oai = AzureOpenAI(
            api_key=cfg.azure_openai_api_key,
            azure_endpoint=cfg.azure_openai_endpoint,
            api_version=cfg.azure_openai_api_version,
        )

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        res = self.oai.embeddings.create(
            model=self.cfg.azure_openai_embed_model,
            input=texts,
        )
        return [d.embedding for d in res.data]

    def upsert_slides(self, ids: List[str], texts: List[str], metadatas: List[Dict[str, Any]]) -> None:
        embeddings = self.embed_texts(texts)
        self.collection.upsert(ids=ids, documents=texts, metadatas=metadatas, embeddings=embeddings)

    def delete_by_doc_hash(self, doc_hash: str) -> None:
        self.collection.delete(where={"doc_hash": doc_hash})

    def delete_ids(self, ids: List[str]) -> None:
        if ids:
            self.collection.delete(ids=ids)

    def update_paths_by_doc_hash(self, doc_hash: str, new_path: str) -> None:
        results = self.collection.get(where={"doc_hash": doc_hash}, include=["documents", "metadatas"])
        if not results or not results.get("ids"):
            return
        ids = results["ids"]
        docs = results["documents"]
        metas = results["metadatas"]
        new_metas = []
        for metadata in metas:
            mm = dict(metadata or {})
            mm["pptx_path"] = new_path
            new_metas.append(mm)
        embeddings = self.embed_texts(docs)
        self.collection.upsert(ids=ids, documents=docs, metadatas=new_metas, embeddings=embeddings)

    def get_source_entries(self, source_root: str) -> List[Dict[str, Any]]:
        results = self.collection.get(where={"source_root": source_root}, include=["metadatas"])
        ids = results.get("ids") or []
        metadatas = results.get("metadatas") or []
        grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"ids": []})
        for slide_id, metadata in zip(ids, metadatas):
            meta = dict(metadata or {})
            doc_uid = meta.get("doc_uid")
            if not doc_uid:
                continue
            entry = grouped[doc_uid]
            entry.setdefault("doc_uid", doc_uid)
            entry.setdefault("doc_signature", meta.get("doc_signature"))
            entry.setdefault("pptx_path", meta.get("pptx_path"))
            entry["ids"].append(slide_id)
        return list(grouped.values())

    def query(self, query_text: str, k: int = 8, source_root: str | None = None) -> Dict[str, Any]:
        q_emb = self.embed_texts([query_text])[0]
        kwargs: Dict[str, Any] = {
            "query_embeddings": [q_emb],
            "n_results": k,
            "include": ["documents", "metadatas", "distances"],
        }
        if source_root:
            kwargs["where"] = {"source_root": source_root}
        return self.collection.query(**kwargs)
