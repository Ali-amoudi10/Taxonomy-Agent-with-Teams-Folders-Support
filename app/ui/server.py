from __future__ import annotations

import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime
import hashlib
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from langchain_core.messages import AIMessage
from pptx.opc.constants import RELATIONSHIP_TYPE as RT

from app.runtime_paths import resource_root
from app.settings import load_settings
from app.preferences import load_preferences, save_preferences
from core.logging import get_logger
from app.graph.build_graph import build_graph
from app.graph.output_schemas import MatchItem, SearchResponse
from app.rag_kb.config import KBConfig
from app.rag_kb.indexer import index_root
from app.rag_kb.teams_indexer import index_teams_source
from app.source_utils import is_probable_sharepoint_url, make_sharepoint_source_key, SourceDescriptor
from app.runtime_paths import user_data_path

import threading

try:
    import pythoncom
    import win32com.client
except Exception:
    pythoncom = None
    win32com = None


app = FastAPI()
RESOURCE_DIR = resource_root() / "app" / "ui"
BASE_DIR = RESOURCE_DIR

app.mount("/static", StaticFiles(directory=str(RESOURCE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(RESOURCE_DIR / "templates"))

settings = load_settings()
graph = build_graph(settings)
logger = get_logger("taxonomy_agent.server")

SESSION: Dict[str, Any] = {
    "directory": "",
    "messages": [],
    "last_results": [],
}

INDEX_STATE: Dict[str, Any] = {
    "status": "idle",
    "directory": "",
    "current": 0,
    "total": 0,
    "percent": 0,
    "current_file": "",
    "message": "No indexing in progress.",
    "stats": {},
    "error": None,
    "run_id": 0,
}
_INDEX_LOCK = threading.Lock()

# ------------------------------------------------------------------
# Teams device-code auth state
# ------------------------------------------------------------------

AUTH_STATE: Dict[str, Any] = {
    "status": "idle",       # idle | pending | complete | error
    "user_code": "",
    "verification_uri": "",
    "message": "",
    "error": None,
}
_AUTH_LOCK = threading.Lock()
_AUTH_STOP = threading.Event()  # set this to cancel an in-progress sign-in

# Pending browser downloads: token -> temp file path
_PENDING_DOWNLOADS: Dict[str, Path] = {}
_DOWNLOADS_LOCK = threading.Lock()


def _get_token_store():
    from app.sharepoint.token_store import TokenStore
    return TokenStore(user_data_path("teams_token.json"))


def _snapshot_auth_state() -> dict[str, Any]:
    with _AUTH_LOCK:
        return dict(AUTH_STATE)


SLIDE_RE = re.compile(r"slide\s*(\d+)(?:\s*/\s*(\d+))?", re.IGNORECASE)
DECK_RE = re.compile(r"deck\s*=\s*([^\n•]+)", re.IGNORECASE)
SNIPPET_RE = re.compile(r"snippet\s*:\s*(.+)", re.IGNORECASE | re.DOTALL)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("[UNHANDLED] %s %s", request.method, request.url.path)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"ok": False, "error": "Internal server error. Check the application log for details."}, status_code=500)
    return JSONResponse({"ok": False, "error": "Internal server error."}, status_code=500)


def _choose_directory_dialog(initial_dir: str = "") -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update()

    try:
        root.lift()
        root.focus_force()
    except Exception:
        pass

    options: dict[str, Any] = {"parent": root}
    if initial_dir and os.path.isdir(initial_dir):
        options["initialdir"] = initial_dir

    path = filedialog.askdirectory(**options)

    try:
        root.attributes("-topmost", False)
    except Exception:
        pass
    root.destroy()
    return str(path or "")


def _choose_save_pptx_path_dialog(initial_dir: str = "", initial_filename: str = "") -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update()

    try:
        root.lift()
        root.focus_force()
    except Exception:
        pass

    options: dict[str, Any] = {
        "parent": root,
        "defaultextension": ".pptx",
        "filetypes": [("PowerPoint presentation", "*.pptx")],
        "confirmoverwrite": True,
    }
    if initial_dir and os.path.isdir(initial_dir):
        options["initialdir"] = initial_dir
    if initial_filename:
        options["initialfile"] = Path(initial_filename).name

    path = filedialog.asksaveasfilename(**options)

    try:
        root.attributes("-topmost", False)
    except Exception:
        pass
    root.destroy()
    return str(path or "")


def _validate_directory(path_value: str) -> str:
    path_str = str(path_value or "").strip()
    if not path_str:
        raise HTTPException(status_code=400, detail="Directory is required.")
    if not os.path.isdir(path_str):
        raise HTTPException(status_code=400, detail="Selected path is not a valid directory.")
    return str(Path(path_str).expanduser().resolve())


def _current_preferences() -> dict[str, Any]:
    return load_preferences()


def _snapshot_index_state() -> dict[str, Any]:
    with _INDEX_LOCK:
        snap = dict(INDEX_STATE)
        snap["stats"] = dict(INDEX_STATE.get("stats") or {})
        snap.pop("run_id", None)
        return snap


def _set_idle_index_state(directory: str = "", message: str = "No indexing in progress.") -> None:
    with _INDEX_LOCK:
        INDEX_STATE.update(
            {
                "status": "idle",
                "directory": directory,
                "current": 0,
                "total": 0,
                "percent": 0,
                "current_file": "",
                "message": message,
                "stats": {},
                "error": None,
            }
        )


def _start_indexing(directory: str) -> dict[str, Any]:
    normalized_dir = str(Path(directory).expanduser().resolve())
    with _INDEX_LOCK:
        INDEX_STATE["run_id"] = int(INDEX_STATE.get("run_id", 0)) + 1
        run_id = INDEX_STATE["run_id"]
        INDEX_STATE.update(
            {
                "status": "indexing",
                "directory": normalized_dir,
                "current": 0,
                "total": 0,
                "percent": 0,
                "current_file": "",
                "message": "Preparing indexing...",
                "stats": {},
                "error": None,
            }
        )

    logger.info("[INDEX] started for %s", normalized_dir)

    def progress_callback(payload: dict[str, Any]) -> None:
        if payload.get("current") or payload.get("stage") in {"done", "scanning"}:
            logger.info("[INDEX] %s", payload)
        with _INDEX_LOCK:
            if INDEX_STATE.get("run_id") != run_id:
                return
            INDEX_STATE.update(
                {
                    "status": payload.get("status", INDEX_STATE.get("status", "indexing")),
                    "directory": normalized_dir,
                    "current": int(payload.get("current", INDEX_STATE.get("current", 0)) or 0),
                    "total": int(payload.get("total", INDEX_STATE.get("total", 0)) or 0),
                    "percent": int(payload.get("percent", INDEX_STATE.get("percent", 0)) or 0),
                    "current_file": payload.get("current_file", INDEX_STATE.get("current_file", "")) or "",
                    "message": payload.get("message", INDEX_STATE.get("message", "")) or "",
                    "stats": dict(payload.get("stats") or INDEX_STATE.get("stats") or {}),
                    "error": payload.get("error"),
                }
            )

    def worker() -> None:
        try:
            result = index_root(normalized_dir, KBConfig(), progress_callback=progress_callback)
            logger.info("[INDEX] completed for %s with stats=%s", normalized_dir, result.get("stats") or {})
            with _INDEX_LOCK:
                if INDEX_STATE.get("run_id") != run_id:
                    return
                INDEX_STATE.update(
                    {
                        "status": "completed",
                        "directory": normalized_dir,
                        "current": INDEX_STATE.get("total", 0),
                        "percent": 100,
                        "current_file": "",
                        "message": "Indexing completed.",
                        "stats": dict(result.get("stats") or {}),
                        "error": None,
                    }
                )
        except Exception as exc:
            logger.exception("[INDEX] failed for %s", normalized_dir)
            with _INDEX_LOCK:
                if INDEX_STATE.get("run_id") != run_id:
                    return
                INDEX_STATE.update(
                    {
                        "status": "error",
                        "directory": normalized_dir,
                        "message": "Indexing failed.",
                        "error": str(exc),
                    }
                )

    thread = threading.Thread(target=worker, daemon=True, name="pptx-indexer")
    thread.start()
    return _snapshot_index_state()


def _same_source(a: str, b: str) -> bool:
    """Compare two source identifiers regardless of whether they are local paths or source keys."""
    if not a or not b:
        return a == b
    if a.startswith("sharepoint::") or b.startswith("sharepoint::"):
        return a == b
    try:
        return str(Path(a).expanduser().resolve()) == str(Path(b).expanduser().resolve())
    except Exception:
        return a == b


def _start_indexing_teams(source: SourceDescriptor, sp_client: Any, mode: str = "download") -> dict[str, Any]:
    source_key = source.source_key
    with _INDEX_LOCK:
        INDEX_STATE["run_id"] = int(INDEX_STATE.get("run_id", 0)) + 1
        run_id = INDEX_STATE["run_id"]
        INDEX_STATE.update(
            {
                "status": "indexing",
                "directory": source_key,
                "current": 0,
                "total": 0,
                "percent": 0,
                "current_file": "",
                "message": "Preparing Teams folder indexing...",
                "stats": {},
                "error": None,
            }
        )

    logger.info("[TEAMS_INDEX] started for %s", source_key)

    def progress_callback(payload: dict[str, Any]) -> None:
        if payload.get("current") or payload.get("stage") in {"done", "scanning", "error"}:
            logger.info("[TEAMS_INDEX] %s", payload)
        with _INDEX_LOCK:
            if INDEX_STATE.get("run_id") != run_id:
                return
            INDEX_STATE.update(
                {
                    "status": payload.get("status", INDEX_STATE.get("status", "indexing")),
                    "directory": source_key,
                    "current": int(payload.get("current", INDEX_STATE.get("current", 0)) or 0),
                    "total": int(payload.get("total", INDEX_STATE.get("total", 0)) or 0),
                    "percent": int(payload.get("percent", INDEX_STATE.get("percent", 0)) or 0),
                    "current_file": payload.get("current_file", INDEX_STATE.get("current_file", "")) or "",
                    "message": payload.get("message", INDEX_STATE.get("message", "")) or "",
                    "stats": dict(payload.get("stats") or INDEX_STATE.get("stats") or {}),
                    "error": payload.get("error"),
                }
            )

    def worker() -> None:
        try:
            result = index_teams_source(source, sp_client, KBConfig(), progress_callback=progress_callback, mode=mode)
            logger.info("[TEAMS_INDEX] completed for %s with stats=%s", source_key, result.get("stats") or {})
            with _INDEX_LOCK:
                if INDEX_STATE.get("run_id") != run_id:
                    return
                INDEX_STATE.update(
                    {
                        "status": "completed",
                        "directory": source_key,
                        "current": INDEX_STATE.get("total", 0),
                        "percent": 100,
                        "current_file": "",
                        "message": "Teams folder indexing completed.",
                        "stats": dict(result.get("stats") or {}),
                        "error": None,
                    }
                )
        except Exception as exc:
            logger.exception("[TEAMS_INDEX] failed for %s", source_key)
            with _INDEX_LOCK:
                if INDEX_STATE.get("run_id") != run_id:
                    return
                INDEX_STATE.update(
                    {
                        "status": "error",
                        "directory": source_key,
                        "message": "Teams folder indexing failed.",
                        "error": str(exc),
                    }
                )

    thread = threading.Thread(target=worker, daemon=True, name="teams-indexer")
    thread.start()
    return _snapshot_index_state()


def _extract_last_assistant_text(messages: list[Any]) -> str:
    for m in reversed(messages or []):
        if isinstance(m, AIMessage):
            c = m.content
            if isinstance(c, str) and c.strip():
                return c.strip()
            if c is not None:
                s = str(c).strip()
                if s:
                    return s

        if isinstance(m, dict) and m.get("role") == "assistant":
            c = m.get("content", "")
            if isinstance(c, str) and c.strip():
                return c.strip()
            if c is not None:
                s = str(c).strip()
                if s:
                    return s

    return ""


def _extract_slide_info_from_reason(reason: str) -> dict[str, Any]:
    out = {
        "slide_number": None,
        "num_slides": None,
        "deck_title": None,
        "snippet": None,
    }

    text = (reason or "").strip()
    if not text:
        return out

    slide_match = SLIDE_RE.search(text)
    if slide_match:
        out["slide_number"] = int(slide_match.group(1))
        if slide_match.group(2):
            out["num_slides"] = int(slide_match.group(2))

    deck_match = DECK_RE.search(text)
    if deck_match:
        out["deck_title"] = deck_match.group(1).strip()

    snippet_match = SNIPPET_RE.search(text)
    if snippet_match:
        out["snippet"] = snippet_match.group(1).strip()

    return out


def _normalize_match(raw: MatchItem | dict[str, Any]) -> dict[str, Any]:
    item = raw if isinstance(raw, MatchItem) else MatchItem.model_validate(raw)
    parsed = _extract_slide_info_from_reason(item.reason)

    return {
        "path": item.path,
        "score": float(item.score),
        "reason": item.reason,
        "slide_number": getattr(item, "slide_number", None) or parsed["slide_number"],
        "num_slides": getattr(item, "num_slides", None) or parsed["num_slides"],
        "deck_title": getattr(item, "deck_title", None) or parsed["deck_title"] or Path(item.path).stem,
        "snippet": getattr(item, "snippet", None) or parsed["snippet"] or item.reason,
    }


def _build_search_text(results: list[dict[str, Any]], error: str | None = None) -> str:
    if error:
        return f"Search completed with an issue: {error}"

    if not results:
        return "No matching slides found."

    lines = [f"I found {len(results)} matching slide(s)."]
    for item in results[:8]:
        deck = item.get("deck_title") or Path(item.get("path", "")).stem or "Untitled deck"
        slide_number = item.get("slide_number")
        score = item.get("score", 0.0)
        # snippet = item.get("snippet") or item.get("reason") or ""
        slide_label = f"Slide {slide_number}" if slide_number else "Slide ?"
        lines.append(f"- {deck} — {slide_label} — score {score:.3f}")
    return "\n".join(lines)


def _sanitize_export_filename(filename: str) -> str:
    candidate = re.sub(r'[<>:"/\\|?*]+', "_", str(filename or "").strip())
    candidate = candidate.rstrip(". ")
    if not candidate:
        candidate = f"taxonomy_deck_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if not candidate.lower().endswith(".pptx"):
        candidate += ".pptx"
    return candidate


def _open_sharepoint_presentation(app_obj: Any, url: str, sp_client: Any, tmp_dir: str) -> Any:
    """Open a SharePoint-hosted PPTX in PowerPoint via COM.

    Tries Option A (direct URL open — zero download) first.  If PowerPoint
    can't authenticate or reach the URL, falls back to downloading the file
    through the Graph API and opening it from a local temp path.
    """
    try:
        logger.info("[EXPORT] opening SharePoint file directly via COM: %s", url)
        return app_obj.Presentations.Open(
            FileName=url,
            ReadOnly=True,
            Untitled=False,
            WithWindow=False,
        )
    except Exception as direct_err:
        logger.warning("[EXPORT] direct COM open failed (%s), falling back to Graph download", direct_err)

    if sp_client is None:
        raise RuntimeError(
            f"PowerPoint could not open {url} directly and no SharePoint client is available for fallback."
        )

    try:
        item = sp_client.resolve_share_link(url)
    except Exception as e:
        raise RuntimeError(f"Cannot resolve SharePoint file URL for download: {e}") from e

    file_bytes = sp_client.download_file(item.drive_id, item.item_id)
    filename = item.name or "source.pptx"
    tmp_path = Path(tmp_dir) / filename
    if tmp_path.exists():
        tmp_path = Path(tmp_dir) / f"{tmp_path.stem}_{item.item_id[:8]}{tmp_path.suffix}"
    tmp_path.write_bytes(file_bytes)
    logger.info("[EXPORT] fallback download saved to %s", tmp_path)

    return app_obj.Presentations.Open(
        FileName=str(tmp_path),
        ReadOnly=True,
        Untitled=False,
        WithWindow=False,
    )


def _build_export_deck(slides: list[dict[str, Any]], export_path: Path, sp_client: Any = None) -> None:
    if pythoncom is None or win32com is None:
        raise RuntimeError("PowerPoint export requires pywin32 and Microsoft PowerPoint on Windows.")

    export_path = Path(export_path).expanduser().resolve()
    export_path.parent.mkdir(parents=True, exist_ok=True)

    pythoncom.CoInitialize()
    app_obj = None
    out_pres = None
    open_sources: dict[str, Any] = {}
    tmp_dir = tempfile.mkdtemp(prefix="taxonomy_export_")

    try:
        app_obj = win32com.client.DispatchEx("PowerPoint.Application")
        app_obj.Visible = 1
        out_pres = app_obj.Presentations.Add(WithWindow=False)

        for item in slides:
            src_path = str(item.get("path") or "").strip()
            slide_number = int(item.get("slide_number") or 0)
            if not src_path or slide_number <= 0:
                logger.warning("[EXPORT] skipping invalid slide: path=%s slide=%s", src_path, slide_number)
                continue

            if src_path not in open_sources:
                is_url = src_path.startswith(("http://", "https://"))
                if is_url:
                    src_pres = _open_sharepoint_presentation(app_obj, src_path, sp_client, tmp_dir)
                elif os.path.isfile(src_path):
                    src_pres = app_obj.Presentations.Open(
                        FileName=str(Path(src_path).resolve()),
                        ReadOnly=True,
                        Untitled=False,
                        WithWindow=False,
                    )
                else:
                    logger.warning("[EXPORT] skipping missing local file: %s", src_path)
                    continue
                open_sources[src_path] = src_pres

            src_pres = open_sources[src_path]
            if slide_number > src_pres.Slides.Count:
                logger.warning("[EXPORT] skipping out-of-range slide %s in %s", slide_number, src_path)
                continue

            src_pres.Slides(slide_number).Copy()
            if out_pres.Slides.Count == 0:
                out_pres.Slides.Paste()
            else:
                out_pres.Slides.Paste(out_pres.Slides.Count + 1)

        if out_pres.Slides.Count == 0:
            raise RuntimeError("No slides were pasted into the destination presentation.")

        out_pres.SaveAs(str(export_path))

    finally:
        for pres in open_sources.values():
            try:
                pres.Close()
            except Exception:
                pass

        if out_pres is not None:
            try:
                out_pres.Close()
            except Exception:
                pass

        if app_obj is not None:
            try:
                app_obj.Quit()
            except Exception:
                pass

        pythoncom.CoUninitialize()
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.get("/api/download_temp/{token}")
async def download_temp_file(token: str):
    """Serve a previously built export deck and delete the temp file afterward."""
    with _DOWNLOADS_LOCK:
        path = _PENDING_DOWNLOADS.pop(token, None)
    if path is None or not Path(path).exists():
        raise HTTPException(status_code=404, detail="Download not found or already retrieved.")
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    def _cleanup():
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            pass

    return FileResponse(
        path=str(path),
        filename=Path(path).name,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        background=BackgroundTask(_cleanup),
    )


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "status": "ready"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    static_inputs = []
    for rel in ("static/app.js", "static/styles.css", "templates/index.html"):
        p = RESOURCE_DIR / rel
        try:
            static_inputs.append(f"{rel}:{int(p.stat().st_mtime_ns)}")
        except FileNotFoundError:
            static_inputs.append(f"{rel}:missing")
    asset_version = hashlib.md5("|".join(static_inputs).encode("utf-8")).hexdigest()[:12]
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"asset_version": asset_version},
    )


@app.get("/api/auth/teams/state")
async def auth_teams_state():
    """Return whether the user is currently signed in to Microsoft."""
    store = _get_token_store()
    return {"ok": True, "signed_in": store.is_signed_in}


@app.post("/api/auth/teams/start")
async def auth_teams_start():
    """Start the device code sign-in flow.

    Returns user_code and verification_uri so the UI can show them to the user.
    Starts a background thread that polls for completion and saves the token.
    """
    import asyncio
    from app.sharepoint.device_auth import start_device_flow, poll_for_token

    tenant_id = settings.sharepoint_tenant_id
    client_id = settings.sharepoint_client_id
    if not (tenant_id and client_id):
        return JSONResponse(
            {
                "ok": False,
                "error": (
                    "SHAREPOINT_TENANT_ID and SHAREPOINT_CLIENT_ID must be set in your "
                    "configuration before signing in."
                ),
            },
            status_code=400,
        )

    # Cancel any existing in-progress sign-in first.
    _AUTH_STOP.set()

    try:
        challenge = await asyncio.to_thread(
            start_device_flow, tenant_id, client_id, settings.sharepoint_verify_tls
        )
    except Exception as exc:
        logger.exception("[AUTH] failed to start device flow")
        return JSONResponse({"ok": False, "error": f"Could not start sign-in: {exc}"}, status_code=500)

    _AUTH_STOP.clear()
    with _AUTH_LOCK:
        AUTH_STATE.update(
            {
                "status": "pending",
                "user_code": challenge.user_code,
                "verification_uri": challenge.verification_uri,
                "message": challenge.message,
                "error": None,
            }
        )

    token_store = _get_token_store()
    client_secret = settings.sharepoint_client_secret or None

    def poll_worker() -> None:
        try:
            payload = poll_for_token(
                tenant_id=tenant_id,
                client_id=client_id,
                device_code=challenge.device_code,
                interval=challenge.interval,
                expires_in=challenge.expires_in,
                client_secret=client_secret,
                verify_tls=settings.sharepoint_verify_tls,
                stop_event=_AUTH_STOP,
            )
            token_store.save_token_response(payload)
            logger.info("[AUTH] device code sign-in completed successfully")
            with _AUTH_LOCK:
                AUTH_STATE.update({"status": "complete", "error": None})
        except Exception as exc:
            logger.warning("[AUTH] device code sign-in failed: %s", exc)
            with _AUTH_LOCK:
                AUTH_STATE.update({"status": "error", "error": str(exc)})

    threading.Thread(target=poll_worker, daemon=True, name="teams-auth-poll").start()

    return {
        "ok": True,
        "user_code": challenge.user_code,
        "verification_uri": challenge.verification_uri,
        "message": challenge.message,
        "expires_in": challenge.expires_in,
    }


@app.get("/api/auth/teams/status")
async def auth_teams_status():
    """Poll this to find out when sign-in is complete."""
    return {"ok": True, "auth": _snapshot_auth_state()}


@app.post("/api/auth/teams/logout")
async def auth_teams_logout():
    """Sign out by clearing the cached token."""
    _AUTH_STOP.set()
    _get_token_store().clear()
    with _AUTH_LOCK:
        AUTH_STATE.update(
            {
                "status": "idle",
                "user_code": "",
                "verification_uri": "",
                "message": "",
                "error": None,
            }
        )
    _AUTH_STOP.clear()
    logger.info("[AUTH] user signed out")
    return {"ok": True}


@app.post("/api/set_dir")
async def set_dir(payload: dict):
    import asyncio

    directory = str(payload.get("directory", "")).strip()
    logger.info("[DIRECTORY] set_dir called with %s", directory or "<empty>")

    if not directory:
        SESSION["directory"] = ""
        SESSION["last_results"] = []
        _set_idle_index_state(message="No directory selected.")
        return {"ok": True, "directory": "", "indexing": _snapshot_index_state()}

    # --- Teams / SharePoint URL ---
    if is_probable_sharepoint_url(directory):
        from app.sharepoint.client import SharePointClient, GraphAuthError

        token_store = _get_token_store()

        # Prefer user token; fall back to app credentials if configured.
        if token_store.is_signed_in:
            sp_client = SharePointClient(settings, token_store=token_store)
        elif settings.sharepoint_client_id and settings.sharepoint_client_secret:
            sp_client = SharePointClient(settings)
        else:
            # No credentials of any kind available — ask the user to sign in.
            return JSONResponse(
                {
                    "ok": False,
                    "error": "not_authenticated",
                    "need_auth": True,
                    "message": (
                        "Sign in to your Microsoft account to access Teams folders. "
                        "Use the Sign in button to get started."
                    ),
                },
                status_code=401,
            )

        try:
            item = await asyncio.to_thread(sp_client.resolve_share_link, directory)
        except GraphAuthError as exc:
            # User token expired and refresh failed — force re-authentication.
            token_store.clear()
            return JSONResponse(
                {
                    "ok": False,
                    "error": "not_authenticated",
                    "need_auth": True,
                    "message": f"Your sign-in expired. Please sign in again. ({exc})",
                },
                status_code=401,
            )
        except Exception as exc:
            logger.exception("[TEAMS] failed to resolve share link %s", directory)
            return JSONResponse(
                {"ok": False, "error": f"Cannot access Teams folder: {exc}"},
                status_code=400,
            )
        if item.kind != "folder":
            return JSONResponse(
                {"ok": False, "error": "The link points to a file, not a folder. Please provide a Teams folder link."},
                status_code=400,
            )
        source_key = make_sharepoint_source_key(item.drive_id, item.item_id)
        source = SourceDescriptor(
            input_value=directory,
            kind="sharepoint",
            source_key=source_key,
            display_name=item.name or item.display_path,
            display_path=item.display_path,
            source_root=source_key,
            drive_id=item.drive_id,
            item_id=item.item_id,
            site_id=item.site_id,
            web_url=item.web_url,
        )
        SESSION["directory"] = source_key
        SESSION["last_results"] = []
        teams_mode = load_preferences().get("teams_indexing_mode", "download")
        indexing = _start_indexing_teams(source, sp_client, mode=teams_mode)
        return {
            "ok": True,
            "directory": source_key,
            "display_name": source.display_name,
            "indexing": indexing,
        }

    # --- Local directory ---
    if not os.path.isdir(directory):
        return JSONResponse({"ok": False, "error": "Directory does not exist."}, status_code=400)

    SESSION["directory"] = directory
    SESSION["last_results"] = []
    indexing = _start_indexing(directory)
    return {"ok": True, "directory": directory, "indexing": indexing}


@app.get("/api/browse_dir")
async def browse_dir():
    try:
        initial_dir = str(SESSION.get("directory", "") or "")
        path = _choose_directory_dialog(initial_dir=initial_dir)
        if not path:
            return {"ok": False, "error": "No directory selected."}
        if not os.path.isdir(path):
            return {"ok": False, "error": "Selected path is not a directory."}

        logger.info("[DIRECTORY] browse selected %s", path)
        SESSION["directory"] = path
        SESSION["last_results"] = []
        indexing = _start_indexing(path)
        return {"ok": True, "directory": path, "indexing": indexing}
    except Exception as e:
        logger.exception("[DIRECTORY] browse failed")
        return {"ok": False, "error": f"Browse not available: {e}"}


@app.get("/api/choose_directory")
async def choose_directory(initial_dir: str = ""):
    try:
        path = _choose_directory_dialog(initial_dir=initial_dir)
        if not path:
            return {"ok": False, "error": "No directory selected."}
        if not os.path.isdir(path):
            return {"ok": False, "error": "Selected path is not a valid directory."}
        resolved = str(Path(path).expanduser().resolve())
        logger.info("[DIRECTORY] chooser returned %s", resolved)
        return {"ok": True, "directory": resolved}
    except Exception as e:
        logger.exception("[DIRECTORY] chooser failed")
        return {"ok": False, "error": f"Directory chooser not available: {e}"}


@app.get("/api/preferences")
async def get_preferences():
    prefs = _current_preferences()
    return {"ok": True, "preferences": prefs}


@app.post("/api/preferences")
async def update_preferences(payload: dict):
    raw_mode = str(payload.get("export_mode", "ask") or "ask").strip().lower()
    export_mode = raw_mode if raw_mode in {"ask", "fixed"} else "ask"
    export_directory = str(payload.get("export_directory", "") or "").strip()

    if export_mode == "fixed":
        if not export_directory:
            return JSONResponse({"ok": False, "error": "Please choose a valid export directory."}, status_code=400)
        if not os.path.isdir(export_directory):
            return JSONResponse({"ok": False, "error": "The export directory is not valid."}, status_code=400)
        export_directory = str(Path(export_directory).expanduser().resolve())
    else:
        export_directory = ""

    raw_teams_mode = str(payload.get("teams_indexing_mode", "download") or "download").strip().lower()
    teams_indexing_mode = raw_teams_mode if raw_teams_mode in {"download", "com"} else "download"

    prefs = save_preferences({
        "export_mode": export_mode,
        "export_directory": export_directory,
        "teams_indexing_mode": teams_indexing_mode,
    })
    logger.info("[PREFERENCES] saved %s", prefs)
    return {"ok": True, "preferences": prefs}


@app.post("/api/reset_database")
async def reset_database():
    """Delete all indexed data from the Chroma database and reset session state."""
    snap = _snapshot_index_state()
    if snap.get("status") in {"indexing", "running"}:
        return JSONResponse(
            {"ok": False, "error": "Indexing is currently in progress. Wait until it finishes before resetting."},
            status_code=409,
        )
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        cfg = KBConfig()
        chroma_client = chromadb.PersistentClient(
            path=cfg.chroma_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        try:
            chroma_client.delete_collection(cfg.collection)
        except Exception:
            pass
        chroma_client.get_or_create_collection(
            name=cfg.collection,
            metadata={"hnsw:space": "cosine"},
        )
        SESSION["directory"] = ""
        SESSION["last_results"] = []
        SESSION["messages"] = []
        _set_idle_index_state(message="Database reset. Select a folder to start indexing.")
        logger.info("[DB] database reset by user")
        return {"ok": True}
    except Exception as e:
        logger.exception("[DB] reset failed")
        return JSONResponse({"ok": False, "error": f"Reset failed: {e}"}, status_code=500)


@app.get("/api/index_status")
async def index_status():
    return {"ok": True, "indexing": _snapshot_index_state()}


@app.post("/api/chat")
async def chat(payload: dict):
    user_msg = str(payload.get("message", "")).strip()
    if not user_msg:
        return JSONResponse({"ok": False, "error": "Empty message."}, status_code=400)

    current_index = _snapshot_index_state()
    current_directory = str(SESSION.get("directory", "") or "").strip()
    if current_directory and _same_source(current_index.get("directory", ""), current_directory) and current_index.get("status") == "indexing":
        progress = f"{current_index.get('current', 0)}/{current_index.get('total', 0)}" if current_index.get("total") else "starting"
        return {
            "ok": True,
            "mode": "chat",
            "text": f"Indexing is still running ({progress}). Please wait until it finishes so search uses the latest directory.",
        }

    logger.info("[USER] %s", user_msg)
    messages = list(SESSION.get("messages") or [])
    messages.append({"role": "user", "content": user_msg})

    state_in = {
        "messages": messages,
        "directory": SESSION.get("directory", ""),
        "last_response": None,
    }

    state_out = graph.invoke(state_in)

    SESSION["messages"] = state_out.get("messages_ui", state_out.get("messages", messages))
    SESSION["directory"] = state_out.get("directory", SESSION.get("directory", ""))

    last_response = state_out.get("last_response")

    if last_response is not None:
        validated = SearchResponse.model_validate(last_response)
        results = [_normalize_match(m) for m in validated.matches]
        SESSION["last_results"] = results

        response_text = _build_search_text(results, validated.error)
        logger.info("[ASSISTANT] %s", response_text)
        return {
            "ok": True,
            "mode": "search",
            "text": response_text,
            "results": results,
        }

    assistant_text = _extract_last_assistant_text(SESSION["messages"])
    if not assistant_text:
        assistant_text = "OK."

    logger.info("[ASSISTANT] %s", assistant_text)
    return {
        "ok": True,
        "mode": "chat",
        "text": assistant_text,
    }


@app.post("/api/export_deck")
async def export_deck(payload: dict):
    import asyncio

    raw_slides = payload.get("slides", [])
    if not isinstance(raw_slides, list) or not raw_slides:
        return JSONResponse({"ok": False, "error": "No slides selected."}, status_code=400)

    slides = [_normalize_match(x) for x in raw_slides]

    has_sharepoint = any(
        str(s.get("path") or "").startswith(("http://", "https://"))
        for s in slides
    )

    # ------------------------------------------------------------------
    # SharePoint / Teams slides → build in temp dir, return browser download
    # ------------------------------------------------------------------
    if has_sharepoint:
        from app.sharepoint.client import SharePointClient

        token_store = _get_token_store()
        if token_store.is_signed_in:
            sp_client = SharePointClient(settings, token_store=token_store)
        elif settings.sharepoint_client_id and settings.sharepoint_client_secret:
            sp_client = SharePointClient(settings)
        else:
            sp_client = None

        filename = _sanitize_export_filename(
            f"taxonomy_deck_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pptx"
        )
        tmp_export_dir = Path(tempfile.gettempdir()) / "taxonomy_exports"
        tmp_export_dir.mkdir(parents=True, exist_ok=True)
        export_path = tmp_export_dir / filename

        try:
            logger.info("[EXPORT] building Teams deck (%s slide(s)) into temp file", len(slides))
            await asyncio.to_thread(_build_export_deck, slides, export_path, sp_client)
        except Exception as e:
            logger.exception("[EXPORT] Teams export failed")
            return JSONResponse({"ok": False, "error": f"Export failed: {e}"}, status_code=500)

        token = str(uuid.uuid4())
        with _DOWNLOADS_LOCK:
            _PENDING_DOWNLOADS[token] = export_path

        logger.info("[EXPORT] Teams deck ready for download: %s (token=%s)", export_path.name, token)
        return {
            "ok": True,
            "filename": filename,
            "download_url": f"/api/download_temp/{token}",
        }

    # ------------------------------------------------------------------
    # Local slides → save to disk (existing behaviour)
    # ------------------------------------------------------------------
    prefs = _current_preferences()
    requested_dir = str(payload.get("target_directory", "") or "").strip()

    filename = _sanitize_export_filename(f"taxonomy_deck_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pptx")
    export_mode = str(prefs.get("export_mode") or "ask").strip().lower()

    if export_mode == "fixed":
        target_directory = requested_dir or str(prefs.get("export_directory") or "").strip()
        if not target_directory:
            return JSONResponse({"ok": False, "error": "Please choose a valid export directory in Settings."}, status_code=400)
        if not os.path.isdir(target_directory):
            return JSONResponse({"ok": False, "error": "Selected export directory is not valid."}, status_code=400)
        export_root = Path(target_directory).expanduser().resolve()
        export_path = export_root / filename
    else:
        if requested_dir:
            if not os.path.isdir(requested_dir):
                return JSONResponse({"ok": False, "error": "Selected export directory is not valid."}, status_code=400)
            export_root = Path(requested_dir).expanduser().resolve()
            export_path = export_root / filename
        else:
            save_path = _choose_save_pptx_path_dialog(initial_dir="", initial_filename=filename)
            if not save_path:
                return JSONResponse({"ok": False, "error": "Export cancelled."}, status_code=400)
            export_path = Path(save_path).expanduser().resolve()
            export_path = export_path.with_name(_sanitize_export_filename(export_path.name))
            export_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("[EXPORT] building local deck with %s slide(s) into %s", len(slides), export_path)
        _build_export_deck(slides, export_path)
    except Exception as e:
        logger.exception("[EXPORT] failed")
        return JSONResponse({"ok": False, "error": f"Export failed: {e}"}, status_code=500)

    logger.info("[EXPORT] saved %s", export_path)
    return {
        "ok": True,
        "filename": export_path.name,
        "saved_path": str(export_path),
        "saved_directory": str(export_path.parent),
    }
