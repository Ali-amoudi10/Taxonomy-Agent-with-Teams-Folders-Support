from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Dict, List

from app.rag_kb.chroma_store import ChromaSlideStore
from app.rag_kb.config import KBConfig
from app.rag_kb.hash_utils import sha256_file
from app.rag_kb.pptx_extract import extract_slides

ProgressCallback = Callable[[dict[str, Any]], None]


def _normalized_root(root: str | Path) -> str:
    return str(Path(root).expanduser().resolve())


def _doc_uid(path: str | Path) -> str:
    resolved = str(Path(path).expanduser().resolve())
    return hashlib.sha1(resolved.encode("utf-8")).hexdigest()


def _doc_signature(path: Path) -> str:
    st = path.stat()
    return f"{st.st_mtime_ns}:{st.st_size}"


def find_pptx_files(root: str | Path) -> List[Path]:
    rootp = Path(root).expanduser().resolve()
    return sorted([p for p in rootp.rglob("*.pptx") if p.is_file()])


def _emit(cb: ProgressCallback | None, **payload: Any) -> None:
    if cb is not None:
        cb(payload)


def index_root(root: str | Path, cfg: KBConfig, progress_callback: ProgressCallback | None = None) -> Dict[str, Any]:
    store = ChromaSlideStore(cfg)
    normalized_root = _normalized_root(root)
    pptx_files = find_pptx_files(normalized_root)

    stats = {
        "indexed_files": 0,
        "indexed_slides": 0,
        "skipped_files": 0,
        "deleted_files": 0,
        "total_files": len(pptx_files),
    }

    _emit(
        progress_callback,
        stage="scanning",
        status="running",
        current=0,
        total=len(pptx_files),
        percent=0,
        current_file="",
        stats=stats.copy(),
        message="Scanning directory for PowerPoint files...",
    )

    existing_entries = store.get_source_entries(normalized_root)
    existing_by_uid = {entry["doc_uid"]: entry for entry in existing_entries if entry.get("doc_uid")}
    current_uids: set[str] = set()

    total = len(pptx_files)
    for index, path in enumerate(pptx_files, start=1):
        current_file = str(path)
        percent = int(index * 100 / total) if total else 100
        _emit(
            progress_callback,
            stage="indexing",
            status="running",
            current=index,
            total=total,
            percent=percent,
            current_file=current_file,
            stats=stats.copy(),
            message=f"Indexing {path.name} ({index}/{total})",
        )

        try:
            doc_uid = _doc_uid(path)
            doc_signature = _doc_signature(path)
            current_uids.add(doc_uid)

            existing = existing_by_uid.get(doc_uid)
            if existing and existing.get("doc_signature") == doc_signature:
                stats["skipped_files"] += 1
                continue

            if existing and existing.get("ids"):
                store.delete_ids(existing["ids"])

            doc_hash = sha256_file(path)
            slides = extract_slides(
                pptx_path=path,
                doc_hash=doc_hash,
                source_root=normalized_root,
                doc_uid=doc_uid,
                doc_signature=doc_signature,
            )
            if not slides:
                stats["skipped_files"] += 1
                continue

            ids = [slide.slide_id for slide in slides]
            texts = [slide.text for slide in slides]
            metas = [slide.metadata for slide in slides]
            store.upsert_slides(ids, texts, metas)

            stats["indexed_files"] += 1
            stats["indexed_slides"] += len(slides)
        except Exception:
            stats["skipped_files"] += 1

    stale_entries = [entry for entry in existing_entries if entry.get("doc_uid") not in current_uids]
    stale_ids = [slide_id for entry in stale_entries for slide_id in entry.get("ids", [])]
    if stale_ids:
        store.delete_ids(stale_ids)
        stats["deleted_files"] = len(stale_entries)

    _emit(
        progress_callback,
        stage="done",
        status="completed",
        current=total,
        total=total,
        percent=100,
        current_file="",
        stats=stats.copy(),
        message="Indexing completed.",
    )
    return {"ok": True, "stats": stats, "root": normalized_root}
