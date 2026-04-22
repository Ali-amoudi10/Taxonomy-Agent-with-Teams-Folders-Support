#!/usr/bin/env python3
from __future__ import annotations
import os
import sys
from pathlib import Path

TREE = {
    "README.md": "",
    "pyproject.toml": "",
    ".env.example": "",
    ".gitignore": "",
    "app": {
        "__init__.py": "",
        "main.py": "",
        "settings.py": "",
        "ui": {
            "server.py": "",
            "static": {
                "styles.css": "",
                "app.js": "",
            },
            "templates": {
                "index.html": "",
            },
        },
        "graph": {
            "build_graph.py": "",
            "state.py": "",
            "prompts.py": "",
            "output_schemas.py": "",
        },
        "services": {
            "file_finder.py": "",
            "pptx_reader.py": "",
            "matcher.py": "",
            "formatter.py": "",
        },
    },
    "core": {
        "__init__.py": "",
        "types.py": "",
        "errors.py": "",
        "logging.py": "",
    },
    "data": {
        "cache": {},
        "temp": {},
        ".gitkeep": "",  # optional convenience so empty dirs are trackable if you want
    },
    "tests": {
        "test_file_finder.py": "",
        "test_pptx_reader.py": "",
        "test_matcher.py": "",
        "test_graph_contracts.py": "",
    },
    "scripts": {
        "dev_run.sh": "#!/usr/bin/env bash\nset -e\npython -m app.main\n",
        "smoke_test.py": "",
    },
}

def create_node(base: Path, spec, name: str | None = None) -> None:
    if isinstance(spec, dict):
        # directory
        d = base / name if name else base
        d.mkdir(parents=True, exist_ok=True)
        for k, v in spec.items():
            create_node(d, v, k)
    else:
        # file
        f = base / name
        f.parent.mkdir(parents=True, exist_ok=True)
        if not f.exists():
            f.write_text(spec if isinstance(spec, str) else "", encoding="utf-8")

def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scaffold.py /path/to/parent_dir")
        return 2

    parent = Path(sys.argv[1]).expanduser().resolve()
    root = parent / "pptx_slide_finder"

    if root.exists() and any(root.iterdir()):
        print(f"Refusing to overwrite non-empty directory: {root}")
        return 1

    root.mkdir(parents=True, exist_ok=True)
    create_node(root, TREE)

    # make dev_run.sh executable on unix-like systems
    dev_run = root / "scripts" / "dev_run.sh"
    try:
        mode = dev_run.stat().st_mode
        dev_run.chmod(mode | 0o111)
    except Exception:
        pass

    print(f"Created project scaffold at: {root}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())