"""Fail closed unless load-test identities and files belong to our factories."""

import json
import re
from hashlib import sha256
from pathlib import Path

from test_data.factories import EMAIL_DOMAIN, ENTITIES, SCHEMA_VERSION, Factory
from test_data.generate import encoded


def verify_dataset(manifest_path):
    path = Path(manifest_path)
    manifest = json.loads(path.read_text())
    factory = Factory(**manifest["factory"])
    expected = {
        "schema_version": SCHEMA_VERSION,
        "synthetic_only": True,
        "factory": manifest["factory"],
        "files": {},
    }
    for entity in ENTITIES:
        generated = sha256()
        for row in factory.rows(entity):
            generated.update(encoded(row))
        expected["files"][entity] = {
            "count": factory.counts[entity],
            "sha256": generated.hexdigest(),
        }
        actual = sha256()
        with (path.parent / f"{entity}.ndjson").open("rb") as stream:
            for block in iter(lambda: stream.read(65536), b""):
                actual.update(block)
        if actual.digest() != generated.digest():
            raise ValueError("Test data differs from deterministic synthetic factory output")
    if manifest != expected:
        raise ValueError("Synthetic manifest does not match the factory")
    return factory


def verify_email(email, factory):
    match = re.fullmatch(r"student-(\d+)-(\d{7})@amaris\.test", email)
    if not match or int(match[1]) != factory.seed or not 0 <= int(match[2]) < factory.students:
        raise ValueError("Login must use a student from the synthetic fixture dataset")
    if factory.row("students", int(match[2]))["email"] != email:
        raise ValueError("Login must exactly match the generated synthetic email")


def verify_identity(body, email):
    if (
        not isinstance(body, dict)
        or body.get("email") != email
        or body.get("authenticated") is not True
        or body.get("emailVerified") is not True
    ):
        raise ValueError("Authenticated session is not the configured verified synthetic student")


def verify_isolation(body):
    if (
        not isinstance(body, dict)
        or body.get("environment") not in ("local", "ci", "staging")
        or body.get("syntheticOnly") is not True
        or body.get("paymentMode") != "mock"
        or body.get("notifications") != "sink"
    ):
        raise ValueError("The server must confirm isolated synthetic data, mock payments and notification sinks")


def verify_data_configuration(env):
    auth = any(
        env.get(name)
        for name in (
            "LOADTEST_AUTH_BEARER",
            "LOADTEST_COOKIE_HEADER",
            "LOADTEST_SESSION_COOKIE_VALUE",
        )
    )
    writes = env.get("LOADTEST_ALLOW_WRITES", "").lower() in ("true", "1", "yes", "on")
    login = env.get("LOADTEST_LOGIN_EMAIL", "")
    if not (auth or writes or login):
        return None
    if env.get("LOADTEST_ENVIRONMENT", "local").strip().lower() not in (
        "local",
        "ci",
        "staging",
    ):
        raise ValueError("Synthetic load-test sessions and writes are restricted to local, CI and staging")
    if not env.get("LOADTEST_DATA_MANIFEST"):
        raise ValueError("Authenticated and write tests require LOADTEST_DATA_MANIFEST")
    factory = verify_dataset(env["LOADTEST_DATA_MANIFEST"])
    verify_email(login, factory)
    if writes and env.get("LOADTEST_REGISTRATION_EMAIL_DOMAIN") != EMAIL_DOMAIN:
        raise ValueError("Registration must use the reserved amaris.test domain and a local email sink")
    if writes and env.get("LOADTEST_PAYMENT_MODE") != "mock":
        raise ValueError("Write load tests require a mock payment adapter")
    return factory
