"""Independent PayFast ITN wire-format regression vectors."""
import hashlib
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
from content.services.payments import (
    HttpPayFastVerificationGateway,
    generate_payfast_itn_signature,
    generate_payfast_signature,
)

class PayFastITNWireFormatTests(SimpleTestCase):
    fields = {
        "m_payment_id": "PF-wire-001",
        "pf_payment_id": "sandbox-001",
        "payment_status": "COMPLETE",
        "item_name": "Algebra ~ revision",
        "custom_str1": "",
        "custom_str2": " Course A ",
        "amount_gross": "950.00",
        "merchant_id": "synthetic-merchant",
    }
    wire = (
        "m_payment_id=PF-wire-001&pf_payment_id=sandbox-001"
        "&payment_status=COMPLETE&item_name=Algebra+%7E+revision"
        "&custom_str1=&custom_str2=+Course+A+&amount_gross=950.00"
        "&merchant_id=synthetic-merchant"
    )
    passphrase = "synthetic-passphrase"

    def signed(self):
        fields = dict(self.fields)
        fields["signature"] = hashlib.md5(
            (self.wire + "&passphrase=" + self.passphrase).encode()
        ).hexdigest()
        return fields

    def test_incoming_signature_preserves_empty_fields_whitespace_and_posted_order(self):
        self.assertEqual(
            generate_payfast_itn_signature(self.fields, self.passphrase),
            self.signed()["signature"],
        )

    def test_checkout_blank_field_filtering_remains_separate(self):
        self.assertEqual(
            generate_payfast_signature({"amount":"950.00","custom_str1":""}),
            hashlib.md5(b"amount=950.00").hexdigest(),
        )

    @patch("content.services.payments._payfast_credentials", return_value=("synthetic-merchant","synthetic-key","synthetic-passphrase"))
    @patch("content.services.payments.urlopen")
    def test_provider_validation_receives_complete_itn_parameter_string(self, urlopen, credentials):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"VALID"
        urlopen.return_value = response
        with patch("content.services.payments._payfast_mode",return_value="sandbox"):
            self.assertTrue(HttpPayFastVerificationGateway().verify_notification(self.signed()))
        request = urlopen.call_args.args[0]
        self.assertEqual(request.data, self.wire.encode())
        self.assertEqual(request.full_url,"https://sandbox.payfast.co.za/eng/query/validate")

    @patch("content.services.payments._payfast_credentials", return_value=("synthetic-merchant","synthetic-key","synthetic-passphrase"))
    @patch("content.services.payments.urlopen")
    def test_blank_field_tampering_is_rejected_before_provider_request(self, urlopen, credentials):
        fields = self.signed()
        fields["custom_str1"] = "changed"
        self.assertFalse(HttpPayFastVerificationGateway().verify_notification(fields))
        urlopen.assert_not_called()

    @patch("content.services.payments._payfast_credentials", return_value=("synthetic-merchant","synthetic-key","synthetic-passphrase"))
    @patch("content.services.payments.urlopen")
    def test_wrong_passphrase_signature_is_rejected_before_provider_request(self, urlopen, credentials):
        fields = self.signed()
        fields["signature"] = hashlib.md5(self.wire.encode()).hexdigest()
        self.assertFalse(HttpPayFastVerificationGateway().verify_notification(fields))
        urlopen.assert_not_called()
