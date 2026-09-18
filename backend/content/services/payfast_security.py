from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import socket
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

PAYFAST_SANDBOX_PROCESS_URL = "https://sandbox.payfast.co.za/eng/process"
PAYFAST_SANDBOX_VALIDATE_URL = "https://sandbox.payfast.co.za/eng/query/validate"
PAYFAST_LIVE_PROCESS_URL = "https://www.payfast.co.za/eng/process"
PAYFAST_LIVE_VALIDATE_URL = "https://www.payfast.co.za/eng/query/validate"
PAYFAST_SANDBOX_SOURCE_HOSTS = ("sandbox.payfast.co.za",)
PAYFAST_LIVE_SOURCE_HOSTS = ("www.payfast.co.za", "w1w.payfast.co.za", "w2w.payfast.co.za")


class PayFastConfigurationError(ValueError):
    """Raised when sandbox verification is configured insecurely."""


@dataclass(frozen=True)
class PayFastConfig:
    """Environment-backed PayFast configuration for sandbox or live hosted checkout."""

    mode: str
    merchant_id: str
    merchant_key: str
    passphrase: str
    return_url: str
    cancel_url: str
    notify_url: str

    def __post_init__(self) -> None:
        mode = self.mode.strip().lower()
        if mode not in {"sandbox", "live"}:
            raise PayFastConfigurationError("PAYFAST_MODE must be either sandbox or live.")
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
            raise PayFastConfigurationError(f"Missing PayFast configuration: {', '.join(sorted(missing))}.")

    @property
    def process_url(self) -> str:
        return PAYFAST_LIVE_PROCESS_URL if self.mode.strip().lower() == "live" else PAYFAST_SANDBOX_PROCESS_URL

    @property
    def validate_url(self) -> str:
        return PAYFAST_LIVE_VALIDATE_URL if self.mode.strip().lower() == "live" else PAYFAST_SANDBOX_VALIDATE_URL

    @property
    def source_hosts(self) -> tuple[str, ...]:
        return PAYFAST_LIVE_SOURCE_HOSTS if self.mode.strip().lower() == "live" else PAYFAST_SANDBOX_SOURCE_HOSTS

    @classmethod
    def from_environment(cls) -> "PayFastConfig":
        return cls(
            mode=os.getenv("PAYFAST_MODE", "sandbox"),
            merchant_id=os.getenv("PAYFAST_MERCHANT_ID", ""),
            merchant_key=os.getenv("PAYFAST_MERCHANT_KEY", ""),
            passphrase=os.getenv("PAYFAST_PASSPHRASE", ""),
            return_url=os.getenv("PAYFAST_RETURN_URL", ""),
            cancel_url=os.getenv("PAYFAST_CANCEL_URL", ""),
            notify_url=os.getenv("PAYFAST_NOTIFY_URL", ""),
        )


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


def build_payfast_checkout_fields(
    checkout_fields: Mapping[str, object],
    *,
    config: PayFastConfig,
    customer_fields: Mapping[str, object] | None = None,
) -> dict[str, str]:
    """Build a signed PayFast hosted-checkout form from backend-owned facts."""

    reference = str(checkout_fields.get("m_payment_id", "")).strip()
    if not reference:
        raise PayFastConfigurationError("Backend checkout field 'm_payment_id' is required.")

    def expand(value: str) -> str:
        return value.replace("{reference}", quote_plus(reference, safe=""))

    fields: dict[str, str] = {
        "merchant_id": config.merchant_id.strip(),
        "merchant_key": config.merchant_key.strip(),
        "return_url": expand(config.return_url.strip()),
        "cancel_url": expand(config.cancel_url.strip()),
        "notify_url": expand(config.notify_url.strip()),
    }
    customer_fields = customer_fields or {}
    for key in ("name_first", "name_last", "email_address", "cell_number"):
        value = str(customer_fields.get(key, "")).strip()
        if value:
            fields[key] = value[:100]

    for key in ("m_payment_id", "amount", "item_name", "custom_str1", "custom_str2"):
        value = str(checkout_fields.get(key, "")).strip()
        if not value:
            raise PayFastConfigurationError(f"Backend checkout field {key!r} is required.")
        fields[key] = value

    fields["signature"] = generate_payfast_signature(fields, passphrase=config.passphrase)
    return fields


def resolve_payfast_source_networks(config: PayFastConfig) -> tuple[str, ...]:
    """Resolve PayFast's documented callback hosts into exact IP networks."""

    networks: set[str] = set()
    for hostname in config.source_hosts:
        try:
            records = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        except OSError:
            continue
        for _family, _socktype, _proto, _canonname, sockaddr in records:
            address = ipaddress.ip_address(sockaddr[0])
            suffix = 32 if address.version == 4 else 128
            networks.add(f"{address}/{suffix}")
    if not networks:
        raise PayFastConfigurationError("PayFast callback source hosts could not be resolved.")
    return tuple(sorted(networks))


def validate_payfast_server(
    payload: Mapping[str, str],
    *,
    config: PayFastConfig,
    timeout: float = 8.0,
) -> bool:
    """Confirm ITN payload data with PayFast's server-to-server validation endpoint."""

    encoded = urlencode([(str(key), str(value)) for key, value in payload.items()]).encode("utf-8")
    request = Request(
        config.validate_url,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "text/plain"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace").strip().upper() == "VALID"
    except TimeoutError:
        raise
    except URLError as exc:
        if isinstance(getattr(exc, "reason", None), TimeoutError):
            raise TimeoutError("PayFast validation timed out.") from exc
        raise ConnectionError("PayFast validation network failure.") from exc
    except OSError as exc:
        raise ConnectionError("PayFast validation network failure.") from exc


class PayFastVerifier:
    """Production-capable PayFast ITN verifier.

    The verifier checks merchant identity, callback source IP, the custom
    integration signature and PayFast's server-to-server validation response.
    """

    def __init__(
        self,
        *,
        config: PayFastConfig,
        source_ip: str,
        allowed_sources: Sequence[str] | None = None,
        valid_data_checker: Callable[[Mapping[str, str]], bool] | None = None,
    ) -> None:
        self.config = config
        self.source_ip = source_ip.strip()
        self.allowed_sources = tuple(allowed_sources or resolve_payfast_source_networks(config))
        self.valid_data_checker = valid_data_checker

    def verify_notification(self, payload: Mapping[str, str]) -> bool:
        if str(payload.get("merchant_id", "")).strip() != self.config.merchant_id.strip():
            return False
        if not self.source_ip or not _source_ip_allowed(self.source_ip, self.allowed_sources):
            return False

        supplied = str(payload.get("signature", "")).strip().lower()
        if len(supplied) != 32:
            return False
        expected = generate_payfast_signature(payload, passphrase=self.config.passphrase)
        if not hmac.compare_digest(supplied, expected):
            return False

        if self.valid_data_checker is not None:
            return bool(self.valid_data_checker(payload))
        return validate_payfast_server(payload, config=self.config)


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
