from app.services.matcher import rank_files

def test_rank_files_basic():
    res = rank_files("finance strategy", [("x.pptx", "Finance roadmap and strategy")], top_k=5)
    assert len(res) == 1
    assert res[0].path.endswith("x.pptx")
    assert res[0].score > 0