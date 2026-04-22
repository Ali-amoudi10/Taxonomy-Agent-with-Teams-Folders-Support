from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from app.settings import Settings


class SourceResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class SourceDescriptor:
    input_value: str
    kind: Literal["local", "sharepoint"]
    source_key: str
    display_name: str
    display_path: str
    source_root: str
    drive_id: str | None = None
    item_id: str | None = None
    site_id: str | None = None
    web_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)



def is_probable_sharepoint_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    host = (parsed.netloc or "").lower()
    return parsed.scheme in {"http", "https"} and ("sharepoint.com" in host or "sharepoint-df.com" in host)



def make_local_source_key(path: str | Path) -> str:
    resolved = str(Path(path).expanduser().resolve())
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()
    return f"local::{digest}"



def make_sharepoint_source_key(drive_id: str, item_id: str) -> str:
    return f"sharepoint::{drive_id}::{item_id}"



def resolve_local_source(source: str) -> SourceDescriptor:
    path = Path(source).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise SourceResolutionError("Directory does not exist.")
    return SourceDescriptor(
        input_value=source,
        kind="local",
        source_key=make_local_source_key(path),
        display_name=path.name or str(path),
        display_path=str(path),
        source_root=str(path),
        web_url=None,
    )



def resolve_source(settings: Settings, source: str, sharepoint_client: Any | None = None) -> SourceDescriptor:
    value = (source or "").strip()
    if not value:
        raise SourceResolutionError("Source is empty.")

    if is_probable_sharepoint_url(value):
        client = sharepoint_client
        if client is None:
            from app.sharepoint.client import SharePointClient

            client = SharePointClient(settings)
        item = client.resolve_share_link(value)
        if item.kind != "folder":
            raise SourceResolutionError("Please provide a SharePoint folder link, not a single file link.")
        return SourceDescriptor(
            input_value=value,
            kind="sharepoint",
            source_key=make_sharepoint_source_key(item.drive_id, item.item_id),
            display_name=item.name,
            display_path=item.display_path or item.name,
            source_root=value,
            drive_id=item.drive_id,
            item_id=item.item_id,
            site_id=item.site_id,
            web_url=item.web_url,
        )

    return resolve_local_source(value)
