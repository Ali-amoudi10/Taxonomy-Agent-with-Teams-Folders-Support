from __future__ import annotations
import sys
from app.services.file_finder import find_pptx_files
from app.services.pptx_reader import extract_text
from app.services.matcher import rank_files

def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/smoke_test.py <directory> <query>")
        return 2

    directory = sys.argv[1]
    query = " ".join(sys.argv[2:])

    files = find_pptx_files(directory, max_files=50)
    texts = [(p, extract_text(p, cache_path="data/cache/pptx_text_cache.json")) for p in files]
    matches = rank_files(query, texts, top_k=5)

    for m in matches:
        print(m.path, m.score, m.reason)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())