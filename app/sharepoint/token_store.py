from __future__ import annotations

import json
import time
from pathlib import Path

import requests


class TokenStore:
    """Persists a Microsoft OAuth2 token (access + refresh) to a local JSON file.

    The file lives at %LOCALAPPDATA%\\TaxonomyAgent\\teams_token.json so it
    survives app restarts but stays on the user's machine only.
    """

    SCOPE = "https://graph.microsoft.com/Files.Read.All offline_access"
    _TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

    def __init__(self, path: Path) -> None:
        self._path = path

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def clear(self) -> None:
        try:
            self._path.unlink(missing_ok=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Token access
    # ------------------------------------------------------------------

    @property
    def is_signed_in(self) -> bool:
        """True if any token data exists (even if the access token is expired)."""
        d = self._load()
        return bool(d.get("access_token") or d.get("refresh_token"))

    def get_valid_access_token(self) -> str | None:
        """Return the cached access token if it is still valid, else None."""
        d = self._load()
        if not d.get("access_token"):
            return None
        if time.time() < float(d.get("expires_at", 0)) - 60:
            return d["access_token"]
        return None

    def save_token_response(self, payload: dict) -> str:
        """Persist a token response dict and return the access token."""
        expires_in = int(payload.get("expires_in", 3600))
        self._save(
            {
                "access_token": payload["access_token"],
                "refresh_token": payload.get("refresh_token"),
                "expires_at": time.time() + expires_in,
            }
        )
        return payload["access_token"]

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    def refresh(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str | None = None,
        verify_tls: bool = True,
    ) -> str | None:
        """Try to get a new access token using the stored refresh token.

        Returns the new access token on success, None if no refresh token is stored.
        Raises RuntimeError if the refresh request is rejected (token revoked, etc.).
        """
        d = self._load()
        refresh_token = d.get("refresh_token")
        if not refresh_token:
            return None

        url = self._TOKEN_URL.format(tenant=tenant_id)
        body: dict = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
            "scope": self.SCOPE,
        }
        if client_secret:
            body["client_secret"] = client_secret

        resp = requests.post(url, data=body, timeout=30, verify=verify_tls)
        payload = resp.json()

        if "access_token" in payload:
            return self.save_token_response(payload)

        # Refresh token was revoked or expired — clear stored data.
        self.clear()
        error_desc = payload.get("error_description") or payload.get("error", "unknown")
        raise RuntimeError(f"Token refresh failed: {error_desc}")
