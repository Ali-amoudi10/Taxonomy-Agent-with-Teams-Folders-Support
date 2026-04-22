from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import requests

from app.settings import Settings

if TYPE_CHECKING:
    from app.sharepoint.token_store import TokenStore


@dataclass
class DriveItemInfo:
    kind: str           # "folder" or "file"
    drive_id: str
    item_id: str
    name: str
    size: int
    last_modified: str  # ISO 8601 datetime string from Graph
    display_path: str
    site_id: str | None
    web_url: str | None


class GraphAuthError(RuntimeError):
    """Raised when we cannot obtain a valid access token."""


class SharePointClient:
    _GRAPH = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        settings: Settings,
        token_store: "TokenStore | None" = None,
    ) -> None:
        """Create a SharePoint client.

        token_store – if provided, use the signed-in user's token (device code
                      auth).  Falls back to token refresh automatically.
                      If None, use app-level client credentials from settings.
        """
        self._settings = settings
        self._token_store = token_store
        # App-credential state (used only when token_store is None)
        self._app_token: str | None = None
        self._app_token_expires_at: float = 0.0
        self._base = (settings.sharepoint_graph_base_url or self._GRAPH).rstrip("/")

    # ------------------------------------------------------------------
    # Token acquisition
    # ------------------------------------------------------------------

    def _ensure_token(self) -> str:
        if self._token_store is not None:
            return self._get_user_token()
        return self._get_app_token()

    def _get_user_token(self) -> str:
        store = self._token_store  # not None here
        token = store.get_valid_access_token()
        if token:
            return token
        # Access token expired – try refresh.
        try:
            token = store.refresh(
                tenant_id=self._settings.sharepoint_tenant_id,
                client_id=self._settings.sharepoint_client_id,
                client_secret=self._settings.sharepoint_client_secret or None,
                verify_tls=self._settings.sharepoint_verify_tls,
            )
        except RuntimeError as exc:
            raise GraphAuthError(
                f"Your Microsoft sign-in has expired and could not be refreshed. "
                f"Please sign in again. ({exc})"
            ) from exc
        if token:
            return token
        raise GraphAuthError(
            "No valid user token found. Please sign in via the Teams authentication flow."
        )

    def _get_app_token(self) -> str:
        if self._app_token and time.monotonic() < self._app_token_expires_at:
            return self._app_token
        self._acquire_app_token()
        return self._app_token  # type: ignore[return-value]

    def _acquire_app_token(self) -> None:
        tenant = self._settings.sharepoint_tenant_id
        client_id = self._settings.sharepoint_client_id
        client_secret = self._settings.sharepoint_client_secret
        if not (tenant and client_id and client_secret):
            raise GraphAuthError(
                "SharePoint app credentials are not configured. "
                "Set SHAREPOINT_TENANT_ID, SHAREPOINT_CLIENT_ID, and SHAREPOINT_CLIENT_SECRET, "
                "or sign in with your Microsoft account first."
            )
        url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
        resp = requests.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=30,
            verify=self._settings.sharepoint_verify_tls,
        )
        resp.raise_for_status()
        payload = resp.json()
        if "access_token" not in payload:
            raise GraphAuthError(
                f"App token request failed: {payload.get('error_description') or payload}"
            )
        self._app_token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3600))
        self._app_token_expires_at = time.monotonic() + expires_in - 60

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._ensure_token()}",
            "Accept": "application/json",
        }

    def _get(self, url: str) -> dict:
        resp = requests.get(
            url,
            headers=self._headers(),
            timeout=self._settings.sharepoint_timeout_seconds,
            verify=self._settings.sharepoint_verify_tls,
        )
        if resp.status_code == 401:
            # Token may have expired mid-request; clear cached token and retry once.
            self._app_token = None
            if self._token_store:
                # Force a refresh on next _ensure_token call.
                pass
            resp = requests.get(
                url,
                headers=self._headers(),
                timeout=self._settings.sharepoint_timeout_seconds,
                verify=self._settings.sharepoint_verify_tls,
            )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Share-link resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_share_url(url: str) -> str:
        # Microsoft's encoding: base64url without padding, prefixed with "u!"
        encoded = base64.b64encode(url.encode("utf-8")).decode("ascii")
        encoded = encoded.rstrip("=").replace("+", "-").replace("/", "_")
        return f"u!{encoded}"

    def resolve_share_link(self, url: str) -> DriveItemInfo:
        """Resolve a SharePoint/Teams sharing URL to a DriveItemInfo."""
        encoded = self._encode_share_url(url)
        data = self._get(f"{self._base}/shares/{encoded}/driveItem")
        return self._parse_item(data)

    # ------------------------------------------------------------------
    # Recursive PPTX listing
    # ------------------------------------------------------------------

    def list_pptx_files(self, drive_id: str, item_id: str) -> list[DriveItemInfo]:
        """Return all .pptx files found recursively under the given folder."""
        results: list[DriveItemInfo] = []
        self._collect_pptx(drive_id, item_id, results)
        return results

    def _collect_pptx(self, drive_id: str, folder_id: str, out: list[DriveItemInfo]) -> None:
        select = "id,name,size,lastModifiedDateTime,folder,file,webUrl,parentReference"
        url: str | None = (
            f"{self._base}/drives/{drive_id}/items/{folder_id}/children?$select={select}"
        )
        while url:
            data = self._get(url)
            for item in data.get("value") or []:
                if "folder" in item:
                    self._collect_pptx(drive_id, item["id"], out)
                elif "file" in item and (item.get("name") or "").lower().endswith(".pptx"):
                    out.append(self._parse_item(item, drive_id=drive_id))
            url = data.get("@odata.nextLink")

    # ------------------------------------------------------------------
    # File download
    # ------------------------------------------------------------------

    def download_file(self, drive_id: str, item_id: str) -> bytes:
        """Download a file's raw bytes via the Graph /content redirect."""
        url = f"{self._base}/drives/{drive_id}/items/{item_id}/content"
        resp = requests.get(
            url,
            headers=self._headers(),
            timeout=self._settings.sharepoint_timeout_seconds,
            verify=self._settings.sharepoint_verify_tls,
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp.content

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_item(self, data: dict, drive_id: str | None = None) -> DriveItemInfo:
        parent_ref = data.get("parentReference") or {}
        effective_drive_id = drive_id or parent_ref.get("driveId") or ""
        # parentReference.path looks like "/drives/<id>/root:/FolderA/FolderB"
        raw_path = (parent_ref.get("path") or "").split("root:", 1)[-1]
        name = data.get("name") or ""
        display_path = (raw_path.rstrip("/") + "/" + name).lstrip("/")
        kind = "folder" if "folder" in data else "file"
        return DriveItemInfo(
            kind=kind,
            drive_id=effective_drive_id,
            item_id=data["id"],
            name=name,
            size=data.get("size") or 0,
            last_modified=data.get("lastModifiedDateTime") or "",
            display_path=display_path,
            site_id=parent_ref.get("siteId"),
            web_url=data.get("webUrl"),
        )
