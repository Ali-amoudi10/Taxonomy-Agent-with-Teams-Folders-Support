# app/graph/state.py
from __future__ import annotations

from typing import Optional, TypedDict

from langgraph.graph.message import MessagesState


class State(MessagesState, total=False):
    """
    MessagesState gives you:
      state["messages"]: list[BaseMessage]
    with a reducer that properly appends messages across nodes.

    We add:
      directory: current root folder for pptx scan/search
      last_response: parsed SearchResponse dict (or None)
    """
    directory: str
    last_response: Optional[dict]