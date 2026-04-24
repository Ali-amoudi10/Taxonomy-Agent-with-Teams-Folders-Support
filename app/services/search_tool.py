from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Optional
import os

from langchain_core.tools import tool

from app.graph.output_schemas import SearchResponse
from app.settings import Settings
from core.logging import get_logger


logger = get_logger("taxonomy_agent.tools")


def is_sharepoint_source(value: str) -> bool:
    return (value or "").startswith("sharepoint::")


def is_under(path: str, root: str) -> bool:
    p = Path(path).expanduser()
    r = Path(root).expanduser()
    try:
        p_res = p.resolve()
        r_res = r.resolve()
        p_res.relative_to(r_res)
        return True
    except ValueError:
        return False


def filter_hits_dynamically(
    hits: list[dict[str, Any]],
    min_score: float,
    relative_margin: float,
    max_results: int,
    max_per_deck: int,
) -> list[dict[str, Any]]:
    if not hits:
        return []

    ranked = sorted(hits, key=lambda item: float(item.get("score", 0.0)), reverse=True)
    best_score = float(ranked[0].get("score", 0.0))
    floor = max(min_score, best_score - relative_margin)

    filtered: list[dict[str, Any]] = []
    seen: set[tuple[str, Any]] = set()
    per_deck: defaultdict[str, int] = defaultdict(int)

    for item in ranked:
        score = float(item.get("score", 0.0))
        if score < floor:
            continue

        path = str(item.get("path") or "")
        slide_number = item.get("slide_number")
        key = (path, slide_number)
        if key in seen:
            continue

        if per_deck[path] >= max_per_deck:
            continue

        seen.add(key)
        per_deck[path] += 1
        filtered.append(item)
        if len(filtered) >= max_results:
            break

    return filtered


def make_search_tool(settings: Settings):
    @tool("search_pptx_library")
    def search_pptx_library(
        query: str,
        directory: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Semantic search for relevant slides under the selected directory."""
        q = (query or "").strip()
        dir_ = (directory or "").strip()
        candidate_k = int(top_k) if top_k is not None else settings.search_candidate_k
        logger.info("[TOOL] search_pptx_library query=%r directory=%r candidate_k=%s", q, dir_, candidate_k)

        if not dir_:
            logger.info("[TOOL] search_pptx_library directory not set")
            return SearchResponse(query=q, directory="", matches=[], error="directory_not_set").model_dump()

        teams_source = is_sharepoint_source(dir_)
        # Single-file mode: a .pptx file path submitted directly (indexed via index_file).
        # index_file stores source_root = str(file_path), so Chroma can filter by it directly.
        single_file = (
            not teams_source
            and dir_.lower().endswith(".pptx")
            and os.path.isfile(dir_)
        )

        if not teams_source and not single_file and not os.path.isdir(dir_):
            logger.info("[TOOL] search_pptx_library directory not found: %s", dir_)
            return SearchResponse(query=q, directory=dir_, matches=[], error="directory_not_found").model_dump()

        # Determine Chroma source_root filter:
        # - Teams and single-file: filter by exact source_root key
        # - Local directory: search globally and filter hits by path below
        chroma_source_root = dir_ if (teams_source or single_file) else None

        try:
            from app.services.semantic_retriever import semantic_slide_search

            hits = semantic_slide_search(
                query=q,
                top_k=candidate_k,
                source_root=chroma_source_root,
            )
        except Exception as e:
            logger.exception("[TOOL] search_pptx_library failed during semantic search")
            return SearchResponse(query=q, directory=dir_, matches=[], error=f"semantic_search_failed: {e}").model_dump()

        if not teams_source and not single_file:
            hits = [hit for hit in hits if isinstance(hit.get("path"), str) and is_under(hit["path"], dir_)]
        hits = filter_hits_dynamically(
            hits=hits,
            min_score=settings.search_min_score,
            relative_margin=settings.search_relative_margin,
            max_results=settings.search_max_results,
            max_per_deck=settings.search_max_per_deck,
        )

        matches = []
        for hit in hits:
            path = hit.get("path") or ""
            score = float(hit.get("score") or 0.0)
            slide_no = hit.get("slide_number")
            num_slides = hit.get("num_slides")
            deck_title = hit.get("deck_title") or ""
            snippet = hit.get("snippet") or ""
            reason = (
                f"slide {slide_no}/{num_slides} • deck={deck_title} • semantic_match\n"
                f"snippet: {snippet}"
            )
            matches.append({"path": path, "score": score, "reason": reason})

        logger.info("[TOOL_RESULT] search_pptx_library returned %s match(es)", len(matches))
        return SearchResponse(query=q, directory=dir_, matches=matches, error=None).model_dump()

    return search_pptx_library
