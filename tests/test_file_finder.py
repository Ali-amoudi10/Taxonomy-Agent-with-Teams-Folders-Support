from app.services.file_finder import find_pptx_files

def test_find_pptx_files_smoke(tmp_path):
    (tmp_path / "a.pptx").write_bytes(b"fake")
    out = find_pptx_files(str(tmp_path), max_files=10)
    assert any(p.endswith("a.pptx") for p in out)