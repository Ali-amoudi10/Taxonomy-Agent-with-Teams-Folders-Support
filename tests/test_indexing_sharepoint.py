from app.source_utils import is_probable_sharepoint_url, make_sharepoint_source_key


def test_sharepoint_utils_basic():
    assert is_probable_sharepoint_url("https://contoso.sharepoint.com/sites/team/Shared%20Documents")
    assert not is_probable_sharepoint_url("C:/slides")
    assert make_sharepoint_source_key("drive-1", "item-2") == "sharepoint::drive-1::item-2"
