from __future__ import annotations

import hashlib
import hmac
import ipaddress
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import quote_plus

PAYFAST_SANDBOX_PROCESS_URL = "https://sandbox.payfast.co.za/eng/process"
PAYFAST_SANDBOX_VALIDATE_URL = "https://sandbox.payfast.co.za/eng/query/validate"


class PayFastConfigurationError(ValueError):
    """Raised when sandbox verification is configured insecurely."""


@dataclass(frozen=True)
class PayFastSandboxConfig:
    """Non-live PayFast configuration used to build signed sandbox requests.

    Credentials are injected by the caller. This module deliberately contains
    no merchant credentials, passphrases, production URLs, or live-money mode.
    """

    merchant_id: str
    merchant_key: str
    passphrase: str
    return_url: str
    cancel_url: str
    notify_url: str

    def __post_init__(self) -> None:
        required = {
            "merchant_id": self.merchant_id,
            "merchant_key": self.merchant_key,
            "passphrase": self.passphrase,
            "return_url": self.return_url,
            "cancel_url": self.cancel_url,
            "notify_url": self.notify_url,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise PayFastConfigurationError(f"Missing PayFast sandbox configuration: {', '.join(sorted(missing))}.")


def _encoded(value: object) -> str:
    return quote_plus(str(value).strip(), safe="")


def generate_payfast_signature(
    fields: Mapping[str, object],
    *,
    passphrase: str,
) -> str:
    """Generate the MD5 signature required by PayFast custom payments/ITNs.

    PayFast custom-payment signatures depend on field order. Python mappings
    preserve insertion order, so callers must supply fields in PayFast's
    documented order. Empty values and the incoming ``signature`` field are
    excluded, and the passphrase is appended only to the signature material.
    """

    parts = []
    for key, value in fields.items():
        if key == "signature" or value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        parts.append(f"{key}={_encoded(text)}")

    phrase = passphrase.strip()
    if phrase:
        parts.append(f"passphrase={_encoded(phrase)}")

    material = "&".join(parts).encode("utf-8")
    return hashlib.md5(material, usedforsecurity=False).hexdigest()


def build_sandbox_checkout_fields(
    checkout_fields: Mapping[str, object],
    *,
    config: PayFastSandboxConfig,
) -> dict[str, str]:
    """Build a signed PayFast sandbox checkout payload.

    The amount, student binding, service binding and payment reference are
    expected to come from the backend-owned checkout session. Browser values
    are not accepted by this helper.
    """

    fields: dict[str, str] = {
        "merchant_id": config.merchant_id.strip(),
        "merchant_key": config.merchant_key.strip(),
        "return_url": config.return_url.strip(),
        "cancel_url": config.cancel_url.strip(),
        "notify_url": config.notify_url.strip(),
    }
    for key in ("m_payment_id", "amount", "item_name", "custom_str1", "custom_str2"):
        value = str(checkout_fields.get(key, "")).strip()
        if not value:
            raise PayFastConfigurationError(f"Backend checkout field {key!r} is required.")
        fields[key] = value

    fields["signature"] = generate_payfast_signature(fields, passphrase=config.passphrase)
    return fields


def _source_ip_allowed(source_ip: str, allowed_sources: Sequence[str]) -> bool:
    try:
        address = ipaddress.ip_address(source_ip.strip())
    except ValueError:
        return False

    for value in allowed_sources:
        try:
            network = ipaddress.ip_network(str(value).strip(), strict=False)
        except ValueError:
            continue
        if address in network:
            return True
    return False


class PayFastSandboxVerifier:
    """Verify a sandbox ITN before the payment domain service can trust it.

    This verifier performs three independent checks without moving real money:
    merchant identity, callback source network, and the PayFast signature. A
    caller-supplied server validator then confirms the ITN data. Tests inject a
    deterministic mock validator; production wiring must use PayFast's current
    server-to-server validation flow and current source-address configuration.
    """

    def __init__(
        self,
        *,
        merchant_id: str,
        passphrase: str,
        source_ip: str,
        allowed_sources: Sequence[str],
        valid_data_checker: Callable[[Mapping[str, str]], bool],
    ) -> None:
        self.merchant_id = merchant_id.strip()
        self.passphrase = passphrase.strip()
        self.source_ip = source_ip.strip()
        self.allowed_sources = tuple(allowed_sources)
        self.valid_data_checker = valid_data_checker
        if not self.merchant_id or not self.passphrase:
            raise PayFastConfigurationError("PayFast sandbox merchant ID and passphrase are required.")
        if not self.source_ip or not self.allowed_sources:
            raise PayFastConfigurationError("PayFast callback source IP and allowed source networks are required.")

    def verify_notification(self, payload: Mapping[str, str]) -> bool:
        if str(payload.get("merchant_id", "")).strip() != self.merchant_id:
            return False
        if not _source_ip_allowed(self.source_ip, self.allowed_sources):
            return False

        supplied = str(payload.get("signature", "")).strip().lower()
        if len(supplied) != 32:
            return False
        expected = generate_payfast_signature(payload, passphrase=self.passphrase)
        if not hmac.compare_digest(supplied, expected):
            return False

        return bool(self.valid_data_checker(payload))
