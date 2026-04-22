from __future__ import annotations

from app.services.search_tool import filter_hits_dynamically


def test_dynamic_filter_returns_only_relevant_hits():
    hits = [
        {"path": "/slides/a.pptx", "slide_number": 1, "score": 0.91},
        {"path": "/slides/b.pptx", "slide_number": 2, "score": 0.88},
        {"path": "/slides/c.pptx", "slide_number": 3, "score": 0.87},
        {"path": "/slides/d.pptx", "slide_number": 4, "score": 0.41},
        {"path": "/slides/e.pptx", "slide_number": 5, "score": 0.39},
    ]

    filtered = filter_hits_dynamically(
        hits=hits,
        min_score=0.30,
        relative_margin=0.08,
        max_results=8,
        max_per_deck=2,
    )

    assert [item["slide_number"] for item in filtered] == [1, 2, 3]


def test_dynamic_filter_limits_per_deck_and_total():
    hits = [
        {"path": "/slides/a.pptx", "slide_number": 1, "score": 0.92},
        {"path": "/slides/a.pptx", "slide_number": 2, "score": 0.91},
        {"path": "/slides/a.pptx", "slide_number": 3, "score": 0.90},
        {"path": "/slides/b.pptx", "slide_number": 1, "score": 0.89},
        {"path": "/slides/c.pptx", "slide_number": 1, "score": 0.88},
    ]

    filtered = filter_hits_dynamically(
        hits=hits,
        min_score=0.30,
        relative_margin=0.10,
        max_results=3,
        max_per_deck=2,
    )

    assert len(filtered) == 3
    assert [item["slide_number"] for item in filtered[:2]] == [1, 2]
