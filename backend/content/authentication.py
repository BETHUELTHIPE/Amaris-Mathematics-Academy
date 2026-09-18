from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.cache import cache
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed


@dataclass(frozen=True)
class SupabasePrincipal:
    id: str
    email: str
    email_verified: bool
    metadata: dict[str, Any]

    @property
    def is_authenticated(self) -> bool:
        return True


class SupabaseBearerAuthentication(BaseAuthentication):
    """Validate a Supabase access token server-to-server without trusting browser claims."""

    cache_seconds = 60

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header:
            return None
        if len(header) != 2 or header[0].lower() != b"bearer":
            raise AuthenticationFailed("Invalid authorization header.")

        try:
            token = header[1].decode("ascii")
        except UnicodeDecodeError as exc:
            raise AuthenticationFailed("Invalid bearer token.") from exc
        if not token:
            raise AuthenticationFailed("Invalid bearer token.")

        principal = self._validate_token(token)
        return principal, None

    def _validate_token(self, token: str) -> SupabasePrincipal:
        supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        publishable_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
        if not supabase_url or not publishable_key:
            raise AuthenticationFailed("Student authentication is unavailable.")

        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        cache_key = f"supabase-auth:{digest}"
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            return self._principal_from_payload(cached)

        auth_request = Request(
            f"{supabase_url}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": publishable_key,
                "Accept": "application/json",
            },
            method="GET",
        )
        timeout = float(os.getenv("SUPABASE_AUTH_TIMEOUT_SECONDS", "4"))
        try:
            with urlopen(auth_request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise AuthenticationFailed("The student session is invalid or expired.") from exc
            raise AuthenticationFailed("Student authentication could not be verified.") from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise AuthenticationFailed("Student authentication could not be verified.") from exc

        principal = self._principal_from_payload(payload)
        cache.set(cache_key, payload, timeout=self.cache_seconds)
        return principal

    @staticmethod
    def _principal_from_payload(payload: dict[str, Any]) -> SupabasePrincipal:
        user_id = str(payload.get("id", "")).strip()
        email = str(payload.get("email", "")).strip().lower()
        if not user_id or not email:
            raise AuthenticationFailed("Student identity is incomplete.")
        metadata = payload.get("user_metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        verified = bool(payload.get("email_confirmed_at") or payload.get("confirmed_at"))
        return SupabasePrincipal(
            id=user_id,
            email=email,
            email_verified=verified,
            metadata=metadata,
        )
