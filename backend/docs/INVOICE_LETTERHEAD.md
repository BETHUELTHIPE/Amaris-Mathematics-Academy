# Required invoice template

Amaris invoices must always use the existing professional academy letterhead
and logo. The reference design is `frontend/components/documents/invoice-document.tsx`,
with `brand-letterhead.tsx` and the academy contact details in `frontend/lib/brand.ts`.

The PDF implementation is `content.services.invoice_document.render_document`.
Course, live-class and video-request invoices all use it. It includes the
navy/blue/gold accent, academy logo, Managing Director, full contact/address/web
band, billed-to details, invoice metadata, item table, totals, payment/help panels
and reference footer. Long content flows to another A4 page with the letterhead
and footer repeated. Packaged fonts support Unicode names and topic text.

Use configured SiteSettings branding when present, with the academy defaults
and packaged website logo otherwise. Do not silently fall back to a plain PDF
when branding assets cannot be loaded. Keep the packaged default logo aligned
with `frontend/public/brand/amaris-academy-icon-192.png`.

Archive the same canonical private PDF that is attached to every recipient's
email and returned by invoice downloads. Issued archive snapshots are retained
across branding changes; a later email retry must not silently replace them.
Do not alter payment verification, invoice numbers, totals, ownership checks or
delivery markers when changing document styling.

`content.test_invoice_letterhead` covers all three invoice types, embedded logo,
complete letterhead, Unicode/long content, repeated page branding and stable
rendering. A preview must be marked **Preview - not issued** and must never be
represented as a payment receipt.
