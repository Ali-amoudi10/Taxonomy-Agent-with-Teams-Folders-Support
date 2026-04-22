from __future__ import annotations
import argparse
import json

from rag_kb.config import KBConfig
from rag_kb.indexer import index_root
from rag_kb.retriever import search_slides

def main():
    p = argparse.ArgumentParser(prog="rag_kb")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_index = sub.add_parser("index", help="Index PPTX slides into Chroma")
    p_index.add_argument("--root", required=True, help="Root folder containing PPTX")
    
    p_query = sub.add_parser("query", help="Semantic query over indexed slides")
    p_query.add_argument("--q", required=True, help="Query text")
    p_query.add_argument("--k", type=int, default=8, help="Top K")

    args = p.parse_args()
    cfg = KBConfig()

    if args.cmd == "index":
        out = index_root(args.root, cfg)
        print(json.dumps(out, indent=2))
        return

    if args.cmd == "query":
        hits = search_slides(args.q, cfg, top_k=args.k)
        print(json.dumps({"ok": True, "hits": hits}, indent=2))
        return

if __name__ == "__main__":
    main()