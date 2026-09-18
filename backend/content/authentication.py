from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import APIException, AuthenticationFailed
from jwt import PyJWKClient, decode as decode_jwt
from jwt.exceptions import PyJWTError

from .models import StudentRecord

GITHUB_OIDC_ISSUER = "https://token.actions.githubusercontent.com"
GITHUB_OIDC_JWKS = "https://token.actions.githubusercontent.com/.well-known/jwks"
GITHUB_ACCEPTANCE_STUDENT_ID = uuid.UUID("00000000-0000-4000-8000-000000009001")
GITHUB_ACCEPTANCE_EMAIL = "acceptance.student@example.test"
_GITHUB_JWK_CLIENT = PyJWKClient(
    GITHUB_OIDC_JWKS,
    cache_keys=True,
    cache_jwk_set=True,
    lifespan=3600,
    timeout=5,
)


class AuthenticationServiceUnavailable(APIException):
    status_code = 503
    default_detail = "Student authentication is temporarily unavailable."
    default_code = "authentication_unavailable"


@dataclass(frozen=True)
class SupabaseStudentPrincipal:
    student: StudentRecord
    supabase_user_id: str
    email: str

    @property
    def id(self):
        return self.student.pk

    @property
    def pk(self):
        return self.student.pk

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False


class SupabaseStudentAuthentication(BaseAuthentication):
    """Validate a Supabase access token against the project's Auth server.

    The project currently uses the legacy shared-secret signing system. Supabase
    recommends server validation through /auth/v1/user in this mode rather than
    duplicating the JWT secret into another backend. Successful validations are
    cached briefly by token hash only; raw bearer tokens are never persisted.
    """

    keyword = b"bearer"

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header:
            return None
        if len(header) != 2 or header[0].lower() != self.keyword:
            raise AuthenticationFailed("Use Authorization: Bearer <access-token>.")

        try:
            token = header[1].decode("ascii")
        except UnicodeDecodeError as exc:
            raise AuthenticationFailed("The access token is malformed.") from exc

        if request.headers.get("X-Amaris-Acceptance", "").strip().lower() == "github-actions":
            return self._authenticate_github_acceptance(token)

        user_payload = self._validate_token(token)
        user_id = str(user_payload.get("id") or "").strip()
        email = str(user_payload.get("email") or "").strip().lower()
        if not user_id or not email:
            raise AuthenticationFailed("The authenticated Supabase user is incomplete.")
        if not user_payload.get("email_confirmed_at"):
            raise AuthenticationFailed("Verify your email before using student services.")

        student = self._get_or_create_student(user_payload, user_id, email)
        if not student.is_active:
            raise AuthenticationFailed("This student profile is inactive.")

        principal = SupabaseStudentPrincipal(
            student=student,
            supabase_user_id=user_id,
            email=email,
        )
        return principal, {"provider": "supabase", "token_sha256": hashlib.sha256(token.encode()).hexdigest()}

    def authenticate_header(self, request):
        return "Bearer"

    def _authenticate_github_acceptance(self, token: str):
        if not bool(getattr(settings, "ACCEPTANCE_GITHUB_OIDC_ENABLED", False)):
            raise AuthenticationFailed("Synthetic acceptance authentication is disabled.")

        audience = str(getattr(settings, "ACCEPTANCE_GITHUB_AUDIENCE", "amaris-staging"))
        expected_repository = str(
            getattr(
                settings,
                "ACCEPTANCE_GITHUB_REPOSITORY",
                "BETHUELTHIPE/Amaris-Mathematics-Academy",
            )
        )
        expected_environment = str(getattr(settings, "ACCEPTANCE_GITHUB_ENVIRONMENT", "staging"))
        expected_ref = str(getattr(settings, "ACCEPTANCE_GITHUB_REF", "refs/heads/main"))

        try:
            signing_key = _GITHUB_JWK_CLIENT.get_signing_key_from_jwt(token).key
            claims = decode_jwt(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=audience,
                issuer=GITHUB_OIDC_ISSUER,
                options={"require": ["exp", "iat", "nbf"]},
            )
        except (PyJWTError, ValueError, TypeError, OSError) as exc:
            raise AuthenticationFailed("The synthetic acceptance identity is invalid.") from exc

        if claims.get("repository") != expected_repository:
            raise AuthenticationFailed("The synthetic acceptance repository is not trusted.")
        if claims.get("event_name") != "push":
            raise AuthenticationFailed("Synthetic acceptance requires a protected main-branch push.")
        if claims.get("environment") != expected_environment:
            raise AuthenticationFailed("Synthetic acceptance requires the staging environment.")
        if expected_ref and claims.get("ref") != expected_ref:
            raise AuthenticationFailed("Synthetic acceptance is restricted to the main branch.")

        student, _ = StudentRecord.objects.update_or_create(
            supabase_user_id=GITHUB_ACCEPTANCE_STUDENT_ID,
            defaults={
                "email": GITHUB_ACCEPTANCE_EMAIL,
                "first_name": "Acceptance",
                "last_name": "Student",
                "is_active": True,
            },
        )
        principal = SupabaseStudentPrincipal(
            student=student,
            supabase_user_id=str(GITHUB_ACCEPTANCE_STUDENT_ID),
            email=GITHUB_ACCEPTANCE_EMAIL,
        )
        return principal, {
            "provider": "github-actions-oidc",
            "repository": claims.get("repository"),
            "run_id": claims.get("run_id"),
            "sha": claims.get("sha"),
        }

    def _validate_token(self, token: str) -> dict:
        url = str(getattr(settings, "SUPABASE_URL", "") or "").rstrip("/")
        publishable_key = str(getattr(settings, "SUPABASE_PUBLISHABLE_KEY", "") or "")
        if not url or not publishable_key:
            raise AuthenticationServiceUnavailable("Supabase authentication is not configured.")

        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        cache_key = f"supabase-auth:{digest}"
        try:
            cached = cache.get(cache_key)
        except Exception:
            cached = None
        if isinstance(cached, dict):
            return cached

        request = Request(
            f"{url}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": publishable_key,
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=float(getattr(settings, "SUPABASE_AUTH_TIMEOUT_SECONDS", 4))) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {400, 401, 403}:
                raise AuthenticationFailed("The student session is invalid or expired.") from exc
            raise AuthenticationServiceUnavailable() from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise AuthenticationServiceUnavailable() from exc

        ttl = max(0, int(getattr(settings, "SUPABASE_AUTH_CACHE_SECONDS", 15)))
        if ttl:
            try:
                cache.set(cache_key, payload, timeout=ttl)
            except Exception:
                pass
        return payload

    @staticmethod
    def _get_or_create_student(payload: dict, user_id: str, email: str) -> StudentRecord:
        metadata = payload.get("user_metadata") if isinstance(payload.get("user_metadata"), dict) else {}
        first_name = str(metadata.get("first_name") or "Student").strip()[:80] or "Student"
        last_name = str(metadata.get("last_name") or "Learner").strip()[:80] or "Learner"

        try:
            student, created = StudentRecord.objects.get_or_create(
                supabase_user_id=user_id,
                defaults={
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                },
            )
        except (IntegrityError, ValueError) as exc:
            raise AuthenticationFailed("The authenticated account could not be linked to a student profile.") from exc

        if not created and student.email != email:
            if StudentRecord.objects.exclude(pk=student.pk).filter(email=email).exists():
                raise AuthenticationFailed("The authenticated email is already linked to another student profile.")
            student.email = email
            student.save(update_fields=["email", "updated_at"])
        return student
