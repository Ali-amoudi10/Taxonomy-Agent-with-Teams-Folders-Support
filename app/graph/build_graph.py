from __future__ import annotations

import json
from typing import Any, Dict, Optional, List

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from app.graph.state import State
from app.graph.llm_factory import get_chat_model
from app.graph.prompts import SYSTEM_PROMPT
from app.settings import Settings
from core.logging import get_logger
from app.services.search_tool import make_search_tool
from app.graph.output_schemas import SearchResponse


def _try_parse_search_response_from_text(text: str) -> Optional[Dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return None

    try:
        data = json.loads(text)
        SearchResponse.model_validate(data)
        return data
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            data = json.loads(candidate)
            SearchResponse.model_validate(data)
            return data
        except Exception:
            return None

    return None


def _extract_fresh_tool_payload(messages: List[BaseMessage]) -> Optional[Dict[str, Any]]:
    """
    Only return a tool payload if a ToolMessage happened *after* the latest user turn.
    This prevents old search results from sticking forever.
    """
    last_human_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            last_human_idx = i
            break

    if last_human_idx is None:
        return None

    for m in reversed(messages[last_human_idx + 1 :]):
        if isinstance(m, ToolMessage):
            content = (m.content or "").strip()
            if not content:
                continue
            try:
                data = json.loads(content)
                SearchResponse.model_validate(data)
                return data
            except Exception:
                continue

    return None


def _strip_tool_messages_for_ui(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in messages:
        if isinstance(m, SystemMessage):
            continue
        if isinstance(m, ToolMessage):
            continue
        if isinstance(m, HumanMessage):
            out.append({"role": "user", "content": m.content or ""})
        elif isinstance(m, AIMessage):
            out.append({"role": "assistant", "content": m.content or ""})
    return out


logger = get_logger("taxonomy_agent.graph")


def build_graph(settings: Settings):
    llm = get_chat_model()

    search_tool = make_search_tool(settings)
    llm_with_tools = llm.bind_tools([search_tool])
    tool_node = ToolNode([search_tool])

    def agent_node(state: State) -> Dict[str, Any]:
        directory = (state.get("directory") or "").strip()

        sys = SystemMessage(
            content=f"{SYSTEM_PROMPT}\n\nCurrent directory: {directory or '(not set)'}"
        )

        msgs = list(state.get("messages") or [])
        ai = llm_with_tools.invoke([sys] + msgs)

        tool_calls = getattr(ai, "tool_calls", None) or []
        if tool_calls:
            for tc in tool_calls:
                logger.info("[TOOL_CALL] name=%s args=%s", tc.get("name"), tc.get("args"))
        else:
            content = (ai.content or "") if isinstance(ai.content, str) else str(ai.content)
            logger.info("[MODEL] %s", content)

        return {"messages": [ai], "directory": directory}

    def finalize_node(state: State) -> Dict[str, Any]:
        directory = (state.get("directory") or "").strip()
        msgs = list(state.get("messages") or [])

        last_response: Optional[Dict[str, Any]] = None

        # 1) Prefer explicit JSON in the final AI message if present.
        if msgs and isinstance(msgs[-1], AIMessage):
            last_response = _try_parse_search_response_from_text(msgs[-1].content or "")

        # 2) Otherwise, only look for a tool result produced after the latest user turn.
        if last_response is None:
            last_response = _extract_fresh_tool_payload(msgs)

        ui_messages = _strip_tool_messages_for_ui(msgs)

        return {
            "directory": directory,
            "messages_ui": ui_messages,
            "last_response": last_response,
        }

    builder = StateGraph(State)

    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: "finalize"})
    builder.add_edge("tools", "agent")
    builder.add_edge("finalize", END)

    return builder.compile()