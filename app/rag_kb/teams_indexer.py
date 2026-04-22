from __future__ import annotations

import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict

from app.rag_kb.chroma_store import ChromaSlideStore
from app.rag_kb.config import KBConfig
from app.rag_kb.pptx_extract import extract_slides
from app.sharepoint.client import DriveItemInfo, SharePointClient
from app.source_utils import SourceDescriptor

logger = logging.getLogger("taxonomy_agent.teams_indexer")

ProgressCallback = Callable[[dict[str, Any]], None]


def _extract_slides_from_pptx_com(
    ppt_app: Any,
    item: DriveItemInfo,
    source_root: str,
    doc_uid: str,
    doc_signature: str,
) -> list:
    """Extract slide text by opening the file directly in a running PowerPoint instance.

    The caller is responsible for creating and quitting the PowerPoint COM application.
    No file is downloaded — PowerPoint streams it from SharePoint.
    """
    from app.rag_kb.pptx_extract import SlideDoc

    url = item.web_url or item.display_path
    deck_title = Path(item.name).stem
    doc_hash = hashlib.sha1(f"com::{doc_uid}".encode()).hexdigest()

    prs = ppt_app.Presentations.Open(
        FileName=url,
        ReadOnly=True,
        Untitled=False,
        WithWindow=False,
    )
    try:
        num_slides = prs.Slides.Count
        slide_docs = []

        for i in range(1, num_slides + 1):
            slide = prs.Slides(i)
            parts: list[str] = []

            for j in range(1, slide.Shapes.Count + 1):
                try:
                    shape = slide.Shapes(j)
                    if shape.HasTextFrame:
                        text = shape.TextFrame.TextRange.Text.strip()
                        if text:
                            parts.append(text)
                except Exception:
                    pass

            try:
                notes_shape = slide.NotesPage.Shapes(2)
                if notes_shape.HasTextFrame:
                    notes_text = notes_shape.TextFrame.TextRange.Text.strip()
                    if notes_text:
                        parts.append("NOTES:\n" + notes_text)
            except Exception:
                pass

            full_text = "\n".join(parts).strip()
            if not full_text:
                continue

            slide_id = f"{doc_uid}::slide::{i}"
            metadata: dict[str, Any] = {
                "doc_hash": doc_hash,
                "doc_uid": doc_uid,
                "doc_signature": doc_signature,
                "source_root": source_root,
                "deck_title": deck_title,
                "pptx_path": url,
                "slide_number": i,
                "num_slides": num_slides,
                "slide_text_hash": hashlib.sha1(full_text.encode()).hexdigest(),
            }
            slide_docs.append(SlideDoc(slide_id=slide_id, text=full_text, metadata=metadata))

        return slide_docs
    finally:
        try:
            prs.Close()
        except Exception:
            pass


def _doc_uid(item_id: str) -> str:
    return hashlib.sha1(f"sharepoint::{item_id}".encode("utf-8")).hexdigest()


def _doc_signature(item: DriveItemInfo) -> str:
    return f"{item.last_modified}:{item.size}"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _emit(cb: ProgressCallback | None, **payload: Any) -> None:
    if cb is not None:
        cb(payload)


def index_teams_source(
    source: SourceDescriptor,
    client: SharePointClient,
    cfg: KBConfig,
    progress_callback: ProgressCallback | None = None,
    mode: str = "download",
) -> Dict[str, Any]:
    """Index all PPTX files in a Teams/SharePoint folder into the local Chroma database.

    mode="download": download each file to a temp path, extract text with python-pptx,
                     then delete immediately. Works without PowerPoint installed.
    mode="com":      open each file directly in desktop PowerPoint via COM — no download.
                     Requires PowerPoint installed and signed in to Microsoft 365.

    source_root stored in Chroma is source.source_key ("sharepoint::driveId::itemId").
    """
    store = ChromaSlideStore(cfg)
    source_root = source.source_key  # "sharepoint::<drive_id>::<item_id>"

    _emit(
        progress_callback,
        stage="scanning",
        status="running",
        current=0,
        total=0,
        percent=0,
        current_file="",
        stats={},
        message="Listing PowerPoint files in Teams folder...",
    )

    try:
        items = client.list_pptx_files(source.drive_id, source.item_id)
    except Exception as exc:
        _emit(
            progress_callback,
            stage="error",
            status="error",
            current=0,
            total=0,
            percent=0,
            current_file="",
            stats={},
            message=f"Failed to list files: {exc}",
            error=str(exc),
        )
        raise

    total = len(items)
    stats: dict[str, Any] = {
        "indexed_files": 0,
        "indexed_slides": 0,
        "skipped_files": 0,
        "deleted_files": 0,
        "total_files": total,
    }

    _emit(
        progress_callback,
        stage="scanning",
        status="running",
        current=0,
        total=total,
        percent=0,
        current_file="",
        stats=stats.copy(),
        message=f"Found {total} PowerPoint file(s) in Teams folder.",
    )

    existing_entries = store.get_source_entries(source_root)
    existing_by_uid: dict[str, dict] = {
        e["doc_uid"]: e for e in existing_entries if e.get("doc_uid")
    }
    current_uids: set[str] = set()

    # ------------------------------------------------------------------ #
    # COM mode: open each file directly in PowerPoint — zero downloads   #
    # ------------------------------------------------------------------ #
    if mode == "com":
        print("Indexing without downloading")
        try:
            import pythoncom
            import win32com.client
        except ImportError:
            raise RuntimeError(
                "pywin32 is required for COM-based indexing. "
                "Install it or switch to Download mode in Settings."
            )

        # Pre-check: figure out which files actually need indexing before
        # launching PowerPoint.  This avoids an expensive PowerPoint startup
        # (and the Visible-property error) when every file is already cached.
        needs_indexing: list = []
        for item in items:
            uid = _doc_uid(item.item_id)
            sig = _doc_signature(item)
            current_uids.add(uid)
            existing = existing_by_uid.get(uid)
            if existing and existing.get("doc_signature") == sig:
                stats["skipped_files"] += 1
            else:
                needs_indexing.append(item)

        if not needs_indexing:
            logger.info(
                "[TEAMS/COM] all %d file(s) already up to date; skipping PowerPoint launch", total
            )
        else:
            pythoncom.CoInitialize()
            ppt_app = None
            n_work = len(needs_indexing)
            try:
                ppt_app = win32com.client.DispatchEx("PowerPoint.Application")
                # Each Presentations.Open call uses WithWindow=False, so we do
                # NOT set app.Visible here — it is redundant and raises an error
                # ("Hiding the application window is not allowed") in some
                # PowerPoint configurations.

                for index, item in enumerate(needs_indexing, start=1):
                    current_file = item.web_url or item.name
                    percent = int(index * 100 / n_work)
                    _emit(
                        progress_callback,
                        stage="indexing",
                        status="running",
                        current=index,
                        total=n_work,
                        percent=percent,
                        current_file=current_file,
                        stats=stats.copy(),
                        message=f"Indexing {item.name} ({index}/{n_work})",
                    )
                    try:
                        uid = _doc_uid(item.item_id)
                        sig = _doc_signature(item)
                        existing = existing_by_uid.get(uid)
                        if existing and existing.get("ids"):
                            store.delete_ids(existing["ids"])

                        slides = _extract_slides_from_pptx_com(ppt_app, item, source_root, uid, sig)
                        if not slides:
                            stats["skipped_files"] += 1
                            continue

                        store.upsert_slides(
                            [s.slide_id for s in slides],
                            [s.text for s in slides],
                            [s.metadata for s in slides],
                        )
                        stats["indexed_files"] += 1
                        stats["indexed_slides"] += len(slides)
                        logger.info("[TEAMS/COM] indexed %s (%d slides)", item.name, len(slides))

                    except Exception as exc:
                        logger.warning("[TEAMS/COM] skipping %s: %s", item.name, exc)
                        stats["skipped_files"] += 1
            finally:
                if ppt_app is not None:
                    try:
                        ppt_app.Quit()
                    except Exception:
                        pass
                pythoncom.CoUninitialize()

    # ------------------------------------------------------------------ #
    # Download mode: download → extract → delete immediately              #
    # ------------------------------------------------------------------ #
    else:
        print("Indexing with downloading")
        with tempfile.TemporaryDirectory() as tmpdir:
            for index, item in enumerate(items, start=1):
                current_file = item.web_url or item.name
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
                    message=f"Indexing {item.name} ({index}/{total})",
                )
                try:
                    uid = _doc_uid(item.item_id)
                    sig = _doc_signature(item)
                    current_uids.add(uid)

                    existing = existing_by_uid.get(uid)
                    if existing and existing.get("doc_signature") == sig:
                        stats["skipped_files"] += 1
                        continue
                    if existing and existing.get("ids"):
                        store.delete_ids(existing["ids"])

                    file_bytes = client.download_file(source.drive_id, item.item_id)
                    tmp_path = Path(tmpdir) / item.name
                    tmp_path.write_bytes(file_bytes)

                    try:
                        doc_hash = _sha256_bytes(file_bytes)
                        slides = extract_slides(
                            pptx_path=tmp_path,
                            doc_hash=doc_hash,
                            source_root=source_root,
                            doc_uid=uid,
                            doc_signature=sig,
                        )
                    finally:
                        tmp_path.unlink(missing_ok=True)

                    display_path = item.web_url or item.display_path
                    deck_title = Path(item.name).stem
                    for slide in slides:
                        slide.metadata["pptx_path"] = display_path
                        slide.metadata["deck_title"] = deck_title

                    if not slides:
                        stats["skipped_files"] += 1
                        continue

                    store.upsert_slides(
                        [s.slide_id for s in slides],
                        [s.text for s in slides],
                        [s.metadata for s in slides],
                    )
                    stats["indexed_files"] += 1
                    stats["indexed_slides"] += len(slides)
                    logger.info("[TEAMS] indexed %s (%d slides)", item.name, len(slides))

                except Exception as exc:
                    logger.warning("[TEAMS] skipping %s: %s", item.name, exc)
                    stats["skipped_files"] += 1

    # Remove entries for files that are no longer in the folder.
    stale = [e for e in existing_entries if e.get("doc_uid") not in current_uids]
    stale_ids = [sid for e in stale for sid in e.get("ids", [])]
    if stale_ids:
        store.delete_ids(stale_ids)
        stats["deleted_files"] = len(stale)

    _emit(
        progress_callback,
        stage="done",
        status="completed",
        current=total,
        total=total,
        percent=100,
        current_file="",
        stats=stats.copy(),
        message="Teams folder indexing completed.",
    )

    logger.info("[TEAMS] indexing done for %s: %s", source_root, stats)
    return {"ok": True, "stats": stats, "source_key": source_root}
