# Amaris Mathematics Academy — official letterhead rule

**Rule:** All formal correspondence from the academy must be written on the existing approved Amaris letterhead. Do not substitute generic, unbranded document layouts.

## Approved branding sources

- Public-site documents: `frontend/components/documents/brand-letterhead.tsx` and `BrandDocumentFooter`.
- Official invoice display: `frontend/components/documents/invoice-document.tsx`; actual archived course/live-class/video PDFs remain generated from the existing Django approved branded invoice workflows. Do not replace their layout or reissue past paid invoices merely to update branding.
- Automated formal HTML email: `backend/content/services/official_letterhead.py`, matching the letterhead's academy identity, logo, tagline, contact details, postal address, website and reference footer.
- Supabase confirmation, one-time sign-in and password recovery: `frontend/email-templates/*.html`, preserving all Supabase-issued `{{ .Token }}` and secure URL placeholders. Never write tokens, passwords or session credentials into source.

## Communications covered

Formal letters, quotations, invoices, receipts, enrolment/registration responses, appointment and booking confirmations, reminders, tutor and sponsor/partner correspondence, payment and video-order messages, notices, reports and certificates. **Account security emails** also use the consistent approved header/footer, but remain concise; authentication details and private attachments must not be exposed.

Keep the sender's contact details and logo as configured in official academy settings. User-generated enquiry content must be HTML escaped. Plain-text email copies remain available for accessibility; the visible HTML email carries the letterhead. Invoice PDFs remain privately archived in the existing student storage workflow and attached only to the authorised recipients.

## Release process

1. Reuse the current logo and approved letterhead, never make a substitute layout.
2. Verify header, footer, approved contact details, correct recipient/reference and attachments.
3. Run the existing unit, letterhead, invoice archival and browser acceptance tests in staging.
4. Update hosted Supabase Auth templates separately via the protected `staging / check` → `staging / apply` workflow and test a real OTP inbox message. Then audit production and obtain explicit production approval before applying there.
5. Do **not** overwrite immutable historic invoices or modify production merely by merging draft code.
