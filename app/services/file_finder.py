from __future__ import annotations
import os
from pathlib import Path
from typing import List

def find_pptx_files(root_dir: str, max_files: int = 200) -> List[str]:
    root = Path(root_dir).expanduser().resolve()
    out: List[str] = []

    if not root.exists():
        return out

    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.startswith("~$"):
                continue
            if fn.lower().endswith(".pptx"):
                out.append(str((Path(dirpath) / fn).resolve()))
                if len(out) >= max_files:
                    return out
    return out