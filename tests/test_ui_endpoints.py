from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("AZURE_OPENAI_API_KEY", "test-key")
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT", "test-deployment")
os.environ.setdefault("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

from fastapi.testclient import TestClient

from app.ui import server


class DummyGraph:
    def invoke(self, state):
        return {
            "messages_ui": state["messages"] + [{"role": "assistant", "content": "done"}],
            "directory": state.get("directory", ""),
            "last_response": {
                "query": state["messages"][-1]["content"],
                "directory": state.get("directory", ""),
                "matches": [
                    {
                        "path": str(Path(state.get("directory", "")) / "deck.pptx"),
                        "score": 0.81,
                        "reason": "slide 2/10 • deck=Deck • semantic_match\nsnippet: finance",
                    }
                ],
                "error": None,
            },
        }


def test_set_dir_starts_indexing(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_start_indexing", lambda directory: {
        "status": "indexing",
        "directory": str(Path(directory).resolve()),
        "current": 0,
        "total": 3,
        "percent": 0,
        "current_file": "",
        "message": "Preparing indexing...",
        "stats": {},
        "error": None,
    })

    client = TestClient(server.app)
    resp = client.post("/api/set_dir", json={"directory": str(tmp_path)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["indexing"]["status"] == "indexing"
    assert body["directory"] == str(tmp_path)


def test_chat_blocks_while_indexing(monkeypatch, tmp_path):
    server.SESSION["directory"] = str(tmp_path)
    monkeypatch.setattr(server, "_snapshot_index_state", lambda: {
        "status": "indexing",
        "directory": str(tmp_path.resolve()),
        "current": 1,
        "total": 4,
        "percent": 25,
        "current_file": str(tmp_path / "a.pptx"),
        "message": "Indexing...",
        "stats": {},
        "error": None,
    })

    client = TestClient(server.app)
    resp = client.post("/api/chat", json={"message": "find finance slides"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "chat"
    assert "Indexing is still running" in body["text"]


def test_chat_search_after_indexing(monkeypatch, tmp_path):
    server.SESSION["directory"] = str(tmp_path)
    server.SESSION["messages"] = []
    monkeypatch.setattr(server, "_snapshot_index_state", lambda: {
        "status": "completed",
        "directory": str(tmp_path.resolve()),
        "current": 1,
        "total": 1,
        "percent": 100,
        "current_file": "",
        "message": "done",
        "stats": {"indexed_files": 1},
        "error": None,
    })
    monkeypatch.setattr(server, "graph", DummyGraph())

    client = TestClient(server.app)
    resp = client.post("/api/chat", json={"message": "find finance slides"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "search"
    assert len(body["results"]) == 1
    assert body["results"][0]["slide_number"] == 2


def test_index_status_endpoint(monkeypatch):
    monkeypatch.setattr(server, "_snapshot_index_state", lambda: {
        "status": "completed",
        "directory": "C:/slides",
        "current": 3,
        "total": 3,
        "percent": 100,
        "current_file": "",
        "message": "Indexing completed.",
        "stats": {"indexed_files": 3},
        "error": None,
    })
    client = TestClient(server.app)
    resp = client.get("/api/index_status")
    assert resp.status_code == 200
    assert resp.json()["indexing"]["status"] == "completed"



def test_preferences_round_trip(monkeypatch, tmp_path):
    saved = {}
    monkeypatch.setattr(server, "load_preferences", lambda: {"export_mode": "ask", "export_directory": ""})
    monkeypatch.setattr(server, "save_preferences", lambda prefs: saved.setdefault("value", prefs) or prefs)

    client = TestClient(server.app)
    resp = client.get("/api/preferences")
    assert resp.status_code == 200
    assert resp.json()["preferences"]["export_mode"] == "ask"

    target_dir = tmp_path / "exports"
    target_dir.mkdir()
    resp = client.post("/api/preferences", json={"export_mode": "fixed", "export_directory": str(target_dir)})
    assert resp.status_code == 200
    assert saved["value"]["export_mode"] == "fixed"
    assert saved["value"]["export_directory"] == str(target_dir.resolve())


def test_export_saves_to_requested_directory(monkeypatch, tmp_path):
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    monkeypatch.setattr(server, "load_preferences", lambda: {"export_mode": "ask", "export_directory": ""})

    def fake_build_export_deck(slides, export_path):
        Path(export_path).write_bytes(b"pptx")

    monkeypatch.setattr(server, "_build_export_deck", fake_build_export_deck)

    client = TestClient(server.app)
    resp = client.post(
        "/api/export_deck",
        json={
            "slides": [
                {
                    "path": str(tmp_path / "deck.pptx"),
                    "score": 0.9,
                    "reason": "slide 1/10 • deck=Deck • semantic_match\nsnippet: finance",
                }
            ],
            "target_directory": str(export_dir),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["saved_directory"] == str(export_dir.resolve())
    assert Path(body["saved_path"]).exists()


def test_export_ask_mode_uses_save_dialog(monkeypatch, tmp_path):
    chosen_path = tmp_path / "custom_name.pptx"

    monkeypatch.setattr(server, "load_preferences", lambda: {"export_mode": "ask", "export_directory": ""})
    monkeypatch.setattr(server, "_choose_save_pptx_path_dialog", lambda initial_dir="", initial_filename="": str(chosen_path))

    def fake_build_export_deck(slides, export_path):
        Path(export_path).write_bytes(b"pptx")

    monkeypatch.setattr(server, "_build_export_deck", fake_build_export_deck)

    client = TestClient(server.app)
    resp = client.post(
        "/api/export_deck",
        json={
            "slides": [
                {
                    "path": str(tmp_path / "deck.pptx"),
                    "score": 0.9,
                    "reason": "slide 1/10 • deck=Deck • semantic_match\nsnippet: finance",
                }
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["saved_path"] == str(chosen_path.resolve())
    assert Path(body["saved_path"]).exists()


def test_export_fixed_mode_uses_fixed_directory(monkeypatch, tmp_path):
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    monkeypatch.setattr(server, "load_preferences", lambda: {"export_mode": "fixed", "export_directory": str(export_dir)})

    def fake_build_export_deck(slides, export_path):
        Path(export_path).write_bytes(b"pptx")

    monkeypatch.setattr(server, "_build_export_deck", fake_build_export_deck)

    client = TestClient(server.app)
    resp = client.post(
        "/api/export_deck",
        json={
            "slides": [
                {
                    "path": str(tmp_path / "deck.pptx"),
                    "score": 0.9,
                    "reason": "slide 1/10 • deck=Deck • semantic_match\nsnippet: finance",
                }
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["saved_directory"] == str(export_dir.resolve())
    assert body["filename"].startswith("taxonomy_deck_")
    assert Path(body["saved_path"]).exists()
