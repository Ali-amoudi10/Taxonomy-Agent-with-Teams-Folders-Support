from __future__ import annotations

import time
from dataclasses import dataclass

import requests


GRAPH_SCOPE = "https://graph.microsoft.com/Files.Read.All offline_access"
_AUTH_BASE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0"


@dataclass
class DeviceCodeChallenge:
    device_code: str
    user_code: str          # short code the user enters at verification_uri
    verification_uri: str   # e.g. https://microsoft.com/devicelogin
    expires_in: int         # seconds until device_code expires
    interval: int           # minimum seconds between polling attempts
    message: str            # human-readable prompt from Microsoft


def start_device_flow(
    tenant_id: str,
    client_id: str,
    verify_tls: bool = True,
) -> DeviceCodeChallenge:
    """Request a device code from Microsoft and return the challenge."""
    url = _AUTH_BASE.format(tenant=tenant_id) + "/devicecode"
    resp = requests.post(
        url,
        data={"client_id": client_id, "scope": GRAPH_SCOPE},
        timeout=30,
        verify=verify_tls,
    )
    resp.raise_for_status()
    d = resp.json()
    if "device_code" not in d:
        raise RuntimeError(
            f"Device code request failed: {d.get('error_description') or d}"
        )
    return DeviceCodeChallenge(
        device_code=d["device_code"],
        user_code=d["user_code"],
        verification_uri=d["verification_uri"],
        expires_in=int(d.get("expires_in", 900)),
        interval=int(d.get("interval", 5)),
        message=d.get("message", ""),
    )


def poll_for_token(
    tenant_id: str,
    client_id: str,
    device_code: str,
    interval: int,
    expires_in: int,
    client_secret: str | None = None,
    verify_tls: bool = True,
    stop_event=None,  # threading.Event – set it to cancel early
) -> dict:
    """Poll the token endpoint until the user completes sign-in.

    Returns the raw token response dict on success.
    Raises RuntimeError on expiry, denial, or any unrecoverable error.
    stop_event (optional threading.Event) can be set externally to abort.
    """
    url = _AUTH_BASE.format(tenant=tenant_id) + "/token"
    body: dict = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": client_id,
        "device_code": device_code,
    }
    if client_secret:
        body["client_secret"] = client_secret

    deadline = time.monotonic() + expires_in
    current_interval = max(interval, 5)

    while time.monotonic() < deadline:
        # Honour a cancellation request.
        if stop_event is not None and stop_event.is_set():
            raise RuntimeError("Sign-in was cancelled.")

        time.sleep(current_interval)

        resp = requests.post(url, data=body, timeout=30, verify=verify_tls)
        payload = resp.json()

        if "access_token" in payload:
            return payload

        error = payload.get("error", "")
        if error == "authorization_pending":
            continue
        elif error == "slow_down":
            current_interval = min(current_interval + 5, 30)
            continue
        elif error in ("expired_token", "bad_verification_code"):
            raise RuntimeError("The sign-in code expired. Please start the sign-in flow again.")
        elif error == "access_denied":
            raise RuntimeError("Sign-in was denied or cancelled by the user.")
        else:
            desc = payload.get("error_description") or error or str(payload)
            raise RuntimeError(f"Sign-in failed: {desc}")

    raise RuntimeError("Sign-in timed out. The device code expired before you signed in.")
