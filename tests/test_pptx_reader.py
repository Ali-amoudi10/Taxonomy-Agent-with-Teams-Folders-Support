def test_pptx_reader_import():
    import app.services.pptx_reader as r
    assert hasattr(r, "extract_text")