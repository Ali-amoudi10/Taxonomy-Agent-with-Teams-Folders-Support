from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List


class MatchItem(BaseModel):
    path: str = Field(..., description="Absolute path to a relevant .pptx file")
    score: float = Field(..., ge=0.0, description="Relevance score (higher is better)")
    reason: str = Field(..., description="Very short reason (few words)")

    # Optional slide-level fields.
    # Your current tool can omit them and the UI will still work.
    slide_number: int | None = Field(default=None, description="1-based slide number in the source deck")
    num_slides: int | None = Field(default=None, description="Total number of slides in the source deck")
    deck_title: str | None = Field(default=None, description="Presentation title / file stem")
    snippet: str | None = Field(default=None, description="Short content snippet from the matched slide")


class SearchResponse(BaseModel):
    query: str
    directory: str
    matches: List[MatchItem] = Field(default_factory=list)
    error: str | None = None