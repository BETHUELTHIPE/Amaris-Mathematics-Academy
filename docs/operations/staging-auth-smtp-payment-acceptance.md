# Staging-only payment-to-Gmail acceptance prerequisites

**Scope:** Render staging service `srv-dam2iivcgkoc7383tq50`, Supabase staging `atyhhjwwxgzeurnwayay`, **PayFast sandbox only**. Production must not be modified. A green **preflight** does not mean users were created or SMTP/payment acceptance passed; inspect the separate guarded job results.

## Current verified state (20 October 2026)

- Supabase staging: 0 Auth users, 0 bookings, 0 payment webhook events, 0 invoices.
- Django staging: no superuser, no Tutors group membership.
- Staging Render sender settings now align with `bethuelmoukangwe8@gmail.com` on Gmail STARTTLS port 587. **An app password is present but has not authenticated successfully**; an email received in Gmail from Gmail itself does not prove Django SMTP delivery.
- Anonymous browser tests pass, but authenticated browser checks require fixture accounts. No PayFast checkout has been made.
- No test data, SMTP authentication or payment is inferred from configuration alone.

## Stage 1 — Protected QA fixture credentials

Use GitHub **Settings → Environments → staging → Environment secrets**, *not* a chat, public repo commit, or workflow input.

Required environment secrets:

- `STAGING_SUPABASE_SERVICE_ROLE_KEY`: a secret/service-role key for the **staging Supabase project only**. Obtain in Supabase staging project API Keys. Never use production service-role keys or expose this in frontend variables.
- `STAGING_TEST_STUDENT_PASSWORD`: random unique password of 24+ characters, created in a password manager.
- `STAGING_TEST_TUTOR_PASSWORD`: different random password of 24+ characters.
- `STAGING_TEST_SUPERUSER_PASSWORD`: third random password of 24+ characters.

The staging public/publishable key can be reused from the verified **staging Render service**; adding `STAGING_SUPABASE_PUBLISHABLE_KEY` as a GitHub staging secret is optional for fixture creation, but **required** for the existing payment/email acceptance workflow. Its value must belong to the staging project.

Create a **staging environment variable** (not secret):
`STAGING_FIXTURE_BOOTSTRAP=CREATE_STAGING_QA_USERS`.

**Never rely on a branch push to create fixtures.** Open [Staging Supabase and Django QA Fixture Setup](https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/actions/workflows/staging-qa-fixtures.yml), click **Run workflow**, select branch `test/staging-fixture-setup-20261020`, and choose **CREATE_STAGING_QA_USERS**. Both that manual selection **and** staging environment variable `STAGING_FIXTURE_BOOTSTRAP=CREATE_STAGING_QA_USERS` are required. Regular push runs and the default `PREFLIGHT_ONLY` option will never create users. The guarded workflow:
1. Asserts exact staging branch, Render service, Supabase database, project ref, PayFast sandbox and protected opt-in.
2. Uses Supabase Auth Admin API to create an approved staging student (`bethuelmoukangwe8@gmail.com`) and isolated staging tutor (`qa-tutor@amaris.test`) with email confirmation for test-only identities.
3. Uses the staging Django ORM to create the Tutors group membership for `amaris_staging_qa_tutor` and staging QA superuser `amaris_staging_qa_admin`.
4. Verifies staging Supabase password grants without logging passwords or access tokens.

**Warning:** Account provisioning is intended to run once only. The bootstrap fails closed on existing QA accounts, and an interrupted two-system write may leave partial staging fixtures; inspect Auth and Django before retrying. Do not repeatedly seed, reset or overwrite an identity. After the initial successful creation, remove the `STAGING_FIXTURE_BOOTSTRAP` environment variable to prevent accidental future approval. The workflow requires the dedicated `STAGING_SUPABASE_SERVICE_ROLE_KEY` staging secret and **will not substitute Render's privileged key**.

## Stage 2 — Real Gmail app password (owner action only)

For the same Google account `bethuelmoukangwe8@gmail.com`, enable two-step verification and create a new Gmail App Password at Google's account security settings (if that option is supported). Store the **new app password** only in:

- Render **staging backend** `EMAIL_HOST_PASSWORD` (merge/edit in Render dashboard, never in chat)
- GitHub **staging Environment secret** `STAGING_SMTP_PASSWORD`
- GitHub **staging Environment secret** `STAGING_GMAIL_IMAP_APP_PASSWORD` for the approved Gmail inbox when IMAP is used.

Ensure GitHub staging environment secrets `STAGING_SMTP_USERNAME`, `STAGING_SMTP_FROM_EMAIL` are exactly `bethuelmoukangwe8@gmail.com`; `STAGING_SMTP_HOST=smtp.gmail.com`, `STAGING_SMTP_PORT=587`. The Render staging backend already has matching sender/login and STARTTLS/587 configured. Do not change the production SMTP account.

To verify the sender without sending anything, use the same [staging QA workflow](https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/actions/workflows/staging-qa-fixtures.yml) → **Run workflow**, branch `test/staging-fixture-setup-20261020` → action **SMTP_AUTH_ONLY**. This requires the protected `STAGING_SMTP_PASSWORD` to equal Render staging `EMAIL_HOST_PASSWORD`, negotiates real Gmail STARTTLS, and authenticates. It **never sends email**. If the runner cannot reach Gmail, the test fails rather than claiming success. A message sent with Gmail directly is not proof of Django SMTP delivery.

## Stage 3 — Real sandbox evidence (never fake a payment)

After secure staging student/tutor/admin login works, a synthetic student must complete **one genuine PayFast sandbox checkout** and the provider must issue the real authenticated ITN. Only then populate the protected GitHub staging acceptance values `STAGING_VERIFIED_BOOKING_REFERENCE` and `STAGING_PAYFAST_SANDBOX_TRANSACTION_ID`.

Use the existing protected **Staging real PayFast live-class email acceptance** workflow. It requires a confirmed paid booking, verifies student ownership and payment authority, downloads the private PDF invoice, dispatches through real Django SMTP and checks the Gmail inbox attachment for the same reference and SHA-256 hash. It must not manufacture a booking, ITN or email proof.

## Keep production unchanged

No production deploy, production database migration, real-money transaction, tutor payout or extra paid service may be initiated by these staging workflows.
