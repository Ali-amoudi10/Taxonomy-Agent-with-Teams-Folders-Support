from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List


@dataclass(frozen=True)
class MemoryConfig:
    """
    Simple message-count sliding window memory.

    - window_messages: how many *most recent* messages to keep.
      (Default 20, but you should pass this from Settings so it's easy to change.)
    """
    window_messages: int = 20


def trim_messages(messages: List[Any], cfg: MemoryConfig) -> List[Any]:
    """
    Keep only the most recent `cfg.window_messages` messages.

    Notes:
    - Works with LangChain message objects OR dict-style messages:
        {"type": "human"|"ai"|"system", "content": "..."}
    - If a system message exists at the beginning, we try to preserve the *latest*
      system message and then keep the last N of the rest.
    - This is intentionally simple for v1. Later you can replace this with:
      - token-based trimming
      - summarization + short memory
      - per-thread memory in a DB
    """
    if not messages:
        return []

    n = max(0, int(cfg.window_messages))
    if n == 0:
        # keep nothing (useful for debugging)
        return []

    if len(messages) <= n:
        return messages

    # Try to preserve the most recent system message (if any)
    last_sys_idx = None
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        # dict style
        if isinstance(m, dict):
            if m.get("type") == "system":
                last_sys_idx = i
                break
        else:
            # LangChain BaseMessage style
            msg_type = getattr(m, "type", None) or getattr(m, "__class__", type("x", (), {})).__name__.lower()
            # In LangChain, BaseMessage.type is usually "system" / "human" / "ai" / "tool"
            if getattr(m, "type", None) == "system" or "system" in str(msg_type):
                last_sys_idx = i
                break

    tail = messages[-n:]

    # If the preserved system message is already included, return tail as-is.
    if last_sys_idx is None:
        return tail

    sys_msg = messages[last_sys_idx]
    if sys_msg in tail:
        return tail

    # Otherwise, prepend it and drop one from the tail to maintain size.
    # (If n==1, we return just the system msg because it’s most important context.)
    if n == 1:
        return [sys_msg]

    return [sys_msg] + tail[-(n - 1):]