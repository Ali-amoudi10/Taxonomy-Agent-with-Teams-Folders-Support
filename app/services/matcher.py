from __future__ import annotations
import re
from typing import Iterable, List, Tuple
from app.graph.output_schemas import MatchItem

_WORD = re.compile(r"[a-zA-Z0-9]+")

def _tokens(s: str) -> List[str]:
    return [t.lower() for t in _WORD.findall(s or "") if len(t) > 1]

def rank_files(query: str, file_texts: Iterable[Tuple[str, str]], top_k: int = 5) -> List[MatchItem]:
    q_tokens = _tokens(query)
    if not q_tokens:
        return []

    q_set = set(q_tokens)
    scored: list[tuple[float, str, str]] = []

    for path, text in file_texts:
        t_tokens = _tokens(text)
        if not t_tokens:
            continue
        t_set = set(t_tokens)

        overlap = q_set.intersection(t_set)
        if not overlap:
            continue

        # v0 scoring: coverage of query terms
        score = len(overlap) / max(1, len(q_set))
        reason_terms = ", ".join(list(sorted(overlap))[:6])
        reason = f"overlap: {reason_terms}" if reason_terms else "keyword overlap"
        scored.append((score, path, reason))

    scored.sort(key=lambda x: x[0], reverse=True)
    out: List[MatchItem] = []
    for score, path, reason in scored[:top_k]:
        out.append(MatchItem(path=path, score=float(score), reason=reason))
    return out