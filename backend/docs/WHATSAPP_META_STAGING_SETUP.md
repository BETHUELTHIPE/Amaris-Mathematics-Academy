# Meta WhatsApp staging account and webhook setup

**Status: HOLD.** On 30 October 2026, Meta's notification for the *Test Messaging Account*
reported that `amaris_booking_confirmation` was moved from **UTILITY** to
**MARKETING**. This notice does not establish the current status of that
template, and no approval evidence has been found for `amaris_class_reminder`.
Do not call either "approved Utility" without a fresh WhatsApp Manager / API check.

This setup is **staging-only**. Keep `WHATSAPP_NOTIFICATIONS_ENABLED=false`
until the complete acceptance suite and separate rollout approval are recorded.
Do not deploy this draft PR into production.

## 1. Confirm correct WhatsApp Business Account (WABA)

1. Log in to Meta Business Manager/WhatsApp Manager for Amaris's
   **Test Messaging Account**, not a different WABA.
2. Navigate to **Message Templates**. Filter for the exact names:
   `amaris_booking_confirmation` and `amaris_class_reminder` and language `en`.
3. Record their current **Status** (must be **APPROVED**) and **Category**
   (must be **UTILITY**) independently. An email about category does not
   prove status or prove a second template exists.
4. If confirmation is **MARKETING**, use Business Support Home ->
   **Template Category Updates** -> **Request Review** (if eligible), or
   submit a strictly transactional new Utility template for review.
   Do not turn on sending while either template is pending/rejected/Marketing.
5. Both templates must use exactly four body placeholders in this order:
   booking reference, topic, SAST start time, tutor name. No promotions or
   public Zoom join link.

## 2. Obtain values securely from Meta

Create or use a system-user access token with only the required scopes.
Meta API listing needs `whatsapp_business_management` and sending later
needs the appropriate messaging permission and sender number access.
Use the correct app, WABA and phone number ID.

**Never add values to a GitHub commit, PR comment, screenshot or chat.**
Store Meta app secret, Graph token and independent webhook verify token only
in Render's staging environment settings/secret manager, with access limited
to staging admins. Rotate any accidentally exposed token.

These keys must be set on the actual **staging Django web service** for the
webhook and on the matching staging notification worker/Beat for dispatch,
according to their roles (avoid giving Beat unnecessary messaging tokens):

| Key | Source | Secret? |
| --- | --- | --- |
| `WHATSAPP_NOTIFICATIONS_ENABLED` | `false` | No |
| `WHATSAPP_GRAPH_API_VERSION` | Supported version in Meta developer dashboard, e.g. `vXX.X` | No |
| `WHATSAPP_WABA_ID` | Meta WhatsApp Business Account ID | No |
| `WHATSAPP_PHONE_NUMBER_ID` | Meta Cloud API sender phone ID | No |
| `WHATSAPP_CLOUD_TOKEN` | Secure system-user access token | **Yes** |
| `WHATSAPP_APP_SECRET` | Meta app secret for signed POST callbacks | **Yes** |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | Newly generated high-entropy random verify token | **Yes** |
| `WHATSAPP_TEMPLATE_LANGUAGE` | `en` (must match approved language exactly) | No |
| `WHATSAPP_CONFIRMATION_TEMPLATE` | `amaris_booking_confirmation` | No |
| `WHATSAPP_REMINDER_TEMPLATE` | `amaris_class_reminder` | No |

The WABA ID is **not** the same as the phone number ID or business portfolio ID.
Do not put the Graph token in a frontend `NEXT_PUBLIC_*` variable or URL.

## 3. Verify without sending any messages

After the draft revision has passed CI, is deployed to an **isolated running
staging environment**, and staging credentials have been added securely:

```bash
cd backend
python manage.py check_whatsapp_staging --webhook-only
python manage.py check_whatsapp_staging
```

- The first command sends no network request to Meta. It invokes the
  Django route internally with a simulated GET challenge, valid signed POST,
  invalid challenge and forged signature to verify local signature handling.
- The second uses a read-only GET to the Meta WABA `/message_templates`
  endpoint, checks `en` records for **APPROVED / UTILITY**, and fails closed
  if either template is missing, pending, rejected or categorized MARKETING.
- Neither command sends a WhatsApp message or enables sending.
- Only template name/category/status and missing **key names** are printed.
  Secrets and token values must never enter CI logs.
- A local preflight **does not prove** that Meta's public webhook subscription,
  HTTPS reachability or real delivery callbacks are operational.

## 4. Connect and verify the external webhook

The Django route is:

`/api/v1/whatsapp/webhook/`

For the existing staging hostname, the intended callback URL is:

`https://amaris-mathematics-academy-staging.onrender.com/api/v1/whatsapp/webhook/`

**Only register it after staging is running the new feature revision.**
The current staging service was reported suspended for **billing** in Render,
and its configured Git branch is older than this draft feature. A suspended
or old service cannot accept the new webhook.

1. In **Meta App Dashboard -> WhatsApp -> Configuration**, set the public
   HTTPS callback URL above.
2. Enter the **same** verify token saved in staging
   `WHATSAPP_WEBHOOK_VERIFY_TOKEN`. Never use the Meta App Secret as the
   verify token: these are independent keys.
3. Save/verify Meta's GET `hub.challenge` handshake. It must return the
   challenge only if the verify token matches.
4. Subscribe to the WhatsApp `messages` field for status and inbound
   STOP messages (and other template-related events if needed).
5. Complete a signed POST delivery receipt and inbound STOP test using
   approved test accounts. The Django view verifies
   `X-Hub-Signature-256` using Meta's **App Secret** before processing events.
6. Verify actual webhook events in staging logs and Django Admin without
   logging full phone numbers, tokens or message bodies. Distinguish Meta
   acceptance from delivered/read receipts.

## 5. Mandatory release gates

- Render account billing suspension resolved; staging web is healthy.
- Staging broker, notification worker and **one** active Beat are healthy.
- Feature branch code, migrations, backend/frontend tests and security gates
  pass, with existing PayFast/invoice emails unaffected.
- Templates both APPROVED / UTILITY in the intended WABA and language.
- Local preflight AND Meta's real public webhook challenge both pass.
- Genuine test PayFast booking sends one consented confirmation and one
  30-minute reminder; delivery receipts and STOP opt-out work.
- Cost, consent/privacy, rollback and production readiness approved.
- Only then consider setting `WHATSAPP_NOTIFICATIONS_ENABLED=true` in
  staging for isolated test recipients; production remains disabled.
