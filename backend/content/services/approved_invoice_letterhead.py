"""Validation of the existing approved Amaris invoice letterhead.

The academy's ReportLab InvoiceDocument renderer sets the PDF Info /Author
metadata to "Amaris Mathematics Academy"; earlier generic PDFs were issued
with /Author (anonymous). Do not replace previously issued objects silently.
"""

from __future__ import annotations

import re


class LegacyInvoiceLetterheadError(ValueError):
    """The immutable stored invoice predates the approved letterhead."""


def require_approved_invoice_letterhead(pdf_bytes: bytes) -> None:
    """Fail closed before delivering or archiving non-approved invoice layouts.

    This is a provenance check for the academy's fixed ReportLab output,
    not a general PDF security validator. It deliberately does not infer
    approval from invoice number, student details, or PDF byte length.
    """

    if not pdf_bytes.startswith(b"%PDF-"):
        raise LegacyInvoiceLetterheadError("Archived invoice is not a PDF.")
    if re.search(rb"/Author\s*\(Amaris Mathematics Academy\)", pdf_bytes) is None:
        raise LegacyInvoiceLetterheadError(
            "Previously issued invoice does not use the approved Amaris letterhead; "
            "administrator must review an audited corrected-invoice procedure."
        )
