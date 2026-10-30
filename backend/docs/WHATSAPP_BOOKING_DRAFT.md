# Draft WhatsApp booking notifications

This is a feature-gated integration using the official Meta WhatsApp Cloud API and Celery. Email notifications are retained.

Staging secrets needed:
- WHATSAPP_NOTIFICATIONS_ENABLED=false initially
- WHATSAPP_GRAPH_API_VERSION
- WHATSAPP_PHONE_NUMBER_ID
- WHATSAPP_CLOUD_TOKEN
- WHATSAPP_TEMPLATE_LANGUAGE=en
- WHATSAPP_CONFIRMATION_TEMPLATE
- WHATSAPP_REMINDER_TEMPLATE

Meta must approve both Utility templates before use. Each body accepts four ordered parameters: booking reference, lesson topic, SAST start time and tutor name.

WhatsAppPreference requires explicit opt-in and E.164 number. Telephone numbers must not automatically imply consent. Student and tutor self-service consent screens are not yet implemented. The reminder scan runs every 60 seconds, using confirmed paid future bookings only. A changed slot will have a new event key.

Release blockers: Verify migration ordering against the current content migration graph; add consent and opt-out interfaces, transient failure retries, provider webhook receipts, end-to-end staging tests, and confirmation of costs. Provider acceptance is not proof of delivery. Do not enable this feature in production without those gates.
