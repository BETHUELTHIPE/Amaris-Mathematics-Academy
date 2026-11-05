"""Read-only Meta template and local webhook preflight for staging.

No live messages are sent and WhatsApp is never enabled by this command.
Credentials are read from environment variables and never displayed.
"""

import hashlib
import hmac
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test.client import RequestFactory
from django.urls import Resolver404, resolve

WEBHOOK_PATH = "/api/v1/whatsapp/webhook/"
REQUIRED_SECRETS = (
    "WHATSAPP_APP_SECRET",
    "WHATSAPP_WEBHOOK_VERIFY_TOKEN",
)
REMOTE_CONFIG = (
    "WHATSAPP_GRAPH_API_VERSION",
    "WHATSAPP_WABA_ID",
    "WHATSAPP_CLOUD_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "WHATSAPP_CONFIRMATION_TEMPLATE",
    "WHATSAPP_REMINDER_TEMPLATE",
)


def _required(names):
    missing = [name for name in names if not os.getenv(name, "").strip()]
    if missing:
        raise CommandError("Missing staging environment keys: " + ", ".join(missing))


def check_webhook():
    """Exercise the Django endpoint's signed GET and POST path locally."""
    _required(REQUIRED_SECRETS)
    try:
        view = resolve(WEBHOOK_PATH).func
    except Resolver404 as exc:
        raise CommandError("WhatsApp webhook URL route is missing.") from exc

    factory = RequestFactory()
    verification_token = os.environ["WHATSAPP_WEBHOOK_VERIFY_TOKEN"]
    challenge = "amaris-preflight-challenge"
    valid_get = factory.get(
        WEBHOOK_PATH,
        data={
            "hub.mode": "subscribe",
            "hub.verify_token": verification_token,
            "hub.challenge": challenge,
        },
        secure=True,
    )
    invalid_get = factory.get(
        WEBHOOK_PATH,
        data={
            "hub.mode": "subscribe",
            "hub.verify_token": "invalid-whatsapp-token",
            "hub.challenge": challenge,
        },
        secure=True,
    )
    response = view(valid_get)
    if response.status_code != 200 or response.content.decode() != challenge:
        raise CommandError("Webhook GET verification challenge failed.")
    if view(invalid_get).status_code != 403:
        raise CommandError("Webhook accepted an invalid verification token.")

    body = b'{"object":"whatsapp_business_account","entry":[]}'
    signature = hmac.new(os.environ["WHATSAPP_APP_SECRET"].encode(), body, hashlib.sha256).hexdigest()
    valid_post = factory.post(
        WEBHOOK_PATH,
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256="sha256=" + signature,
        secure=True,
    )
    invalid_post = factory.post(
        WEBHOOK_PATH,
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256="sha256=invalid",
        secure=True,
    )
    if view(valid_post).status_code != 200:
        raise CommandError("Webhook refused a correctly signed POST.")
    if view(invalid_post).status_code != 403:
        raise CommandError("Webhook accepted a forged POST signature.")


def fetch_templates():
    """Retrieve Meta template status/category directly, with no send calls."""
    _required(REMOTE_CONFIG)
    version = os.environ["WHATSAPP_GRAPH_API_VERSION"].strip()
    waba_id = os.environ["WHATSAPP_WABA_ID"].strip()
    if not re.fullmatch(r"v[0-9]+\.[0-9]+", version):
        raise CommandError("WHATSAPP_GRAPH_API_VERSION must be vMAJOR.MINOR.")
    if not waba_id.isdecimal():
        raise CommandError("WHATSAPP_WABA_ID must contain digits only.")
    language = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "en").strip()
    wanted = {
        os.environ["WHATSAPP_CONFIRMATION_TEMPLATE"].strip(),
        os.environ["WHATSAPP_REMINDER_TEMPLATE"].strip(),
    }
    if len(wanted) != 2:
        raise CommandError("Confirmation and reminder must use distinct templates.")

    seen = {}
    after = None
    cursors = set()
    for _page in range(20):
        query = {
            "fields": "name,status,category,language",
            "limit": "100",
        }
        if after:
            query["after"] = after
        url = f"https://graph.facebook.com/{version}/{waba_id}/message_templates?" + urlencode(query)
        request = Request(
            url,
            headers={"Authorization": f"Bearer {os.environ['WHATSAPP_CLOUD_TOKEN']}", "Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=15) as response:
                payload = json.load(response)
        except HTTPError as exc:
            # Never print URL, response body, access token or account ID.
            raise CommandError(f"Meta template lookup failed (HTTP {exc.code}).") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise CommandError("Unable to retrieve Meta template status securely.") from None

        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise CommandError("Unexpected Meta template response.")

        for item in payload["data"]:
            if not isinstance(item, dict):
                continue
            if item.get("name") in wanted and item.get("language") == language:
                seen[item["name"]] = {
                    "status": str(item.get("status", "UNKNOWN")).upper(),
                    "category": str(item.get("category", "UNKNOWN")).upper(),
                }
        # Never follow arbitrary API-provided next links: rebuild the trusted
        # graph.facebook.com URL using just the cursor.
        paging = payload.get("paging") or {}
        next_page = paging.get("next") if isinstance(paging, dict) else None
        next_cursor = (paging.get("cursors") or {}).get("after") if isinstance(paging, dict) else None
        if not next_page or not next_cursor:
            break
        if next_cursor in cursors:
            raise CommandError("Meta template pagination loop detected.")
        cursors.add(next_cursor)
        after = next_cursor
    else:
        raise CommandError("Meta template listing exceeds preflight page limit.")
    return {name: seen.get(name) for name in sorted(wanted)}


class Command(BaseCommand):
    help = "Safely verify Meta Utility templates and local signed webhook without sending messages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--webhook-only",
            action="store_true",
            help="Test webhook challenge/signature locally without querying the Graph API.",
        )

    def handle(self, *args, **options):
        if getattr(settings, "WHATSAPP_NOTIFICATIONS_ENABLED", False):
            raise CommandError("Refusing preflight while WhatsApp sending is enabled.")
        check_webhook()
        self.stdout.write("Local webhook challenge and HMAC verification: PASS.")
        if options["webhook_only"]:
            return
        templates = fetch_templates()
        bad = []
        for name, record in templates.items():
            if record is None:
                self.stdout.write(f"{name}: MISSING for selected language.")
                bad.append(name)
            else:
                self.stdout.write(f"{name}: {record['status']} / {record['category']}.")
                if record["status"] != "APPROVED" or record["category"] != "UTILITY":
                    bad.append(name)
        if bad:
            raise CommandError("Staging blocked: both templates must be APPROVED / UTILITY before sending.")
        self.stdout.write(self.style.SUCCESS("Both Meta Utility templates verified. Sending remains disabled."))
