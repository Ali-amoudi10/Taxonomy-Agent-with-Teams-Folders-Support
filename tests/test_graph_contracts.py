from app.services.search_tool import make_search_tool
from app.settings import load_settings
from app.graph.output_schemas import SearchResponse


def test_search_tool_returns_directory_not_set():
    settings = load_settings()
    tool = make_search_tool(settings)
    out = tool.invoke({"query": "topic", "directory": ""})
    resp = SearchResponse.model_validate(out)
    assert resp.error == "directory_not_set"
