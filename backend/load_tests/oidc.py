"""Renew the short-lived GitHub Actions credential during staging capacity runs."""

import json
import threading
import time
from urllib.request import Request, urlopen


class ActionsOidcBearer:
    def __init__(
        self,
        *,
        initial_token: str,
        request_url: str,
        request_token: str,
        audience: str = "amaris-staging",
        refresh_seconds: int = 90,
    ) -> None:
        self._token = initial_token
        self._request_url = request_url
        self._request_token = request_token
        self._audience = audience
        self._refresh_seconds = refresh_seconds
        self._refresh_at = time.monotonic() + refresh_seconds
        self._lock = threading.Lock()

    def current(self) -> str:
        if not (self._request_url and self._request_token):
            return self._token
        if time.monotonic() < self._refresh_at:
            return self._token
        with self._lock:
            if time.monotonic() >= self._refresh_at:
                separator = "&" if "?" in self._request_url else "?"
                request = Request(
                    f"{self._request_url}{separator}audience={self._audience}",
                    headers={"Authorization": f"Bearer {self._request_token}"},
                )
                with urlopen(request, timeout=10) as response:
                    token = json.load(response).get("value", "")
                if not isinstance(token, str) or not token:
                    raise RuntimeError("GitHub Actions did not issue a staging OIDC token.")
                self._token = token
                self._refresh_at = time.monotonic() + self._refresh_seconds
        return self._token
