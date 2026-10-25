# Amaris student six-digit email verification and sign-in

This project uses **Supabase Auth** to generate, deliver, expire and verify email OTPs. Amaris never generates OTPs itself, saves them in Django/Next.js, or writes them to logs.

## Required production Supabase configuration

Project: `epkcuseloinygkakxxdu` (Amaris production). In the Supabase Dashboard go to **Authentication → Email Templates**:

1. **Confirm sign up**: paste the contents of `frontend/email-templates/confirm-signup.html`, set subject `Amaris | Verify your student email`. Retain `{{ .Token }}` so the email **contains the actual OTP**, and `{{ .ConfirmationURL }}` for the existing link path.
2. **Magic Link** (also used for email OTP login): paste `frontend/email-templates/magic-link-login.html`, set subject `Amaris | Your six-digit sign-in code`. Retain `{{ .Token }}` so `signInWithOtp` sends a **numeric code**, not only a link. The link uses the safe server-side `/auth/confirm` route.
3. **Authentication → Providers → Email**: enable **Confirm email** and verify **Email OTP length = 6** digits (Supabase's documented default); limit expiry to 10 minutes when available, otherwise no more than the platform default of one hour. Keep request rate limits and anti-abuse controls enabled.
4. **Authentication → SMTP Settings**: use a legitimate verified sender and production-grade custom SMTP. This is **Supabase Auth SMTP**, which is separate from Django's `EMAIL_HOST` for booking confirmations. Supabase's default email service is best-effort and rate-limited, not appropriate for routine student registration.
5. **Authentication → URL Configuration**: set the live student frontend as the Site URL and allow the exact production `/auth/confirm` callback and staging callback URLs as appropriate. Avoid broadly permissive redirect patterns.
6. Apply and verify staging configuration before adjusting production. Never paste SMTP secrets into source control or ChatGPT.

The current Supabase connector cannot read or update Auth email template HTML or authenticated SMTP settings; the files here are **deployment-ready templates**, not proof that dashboard templates are already installed. Do not claim actual email delivery from passing code tests.

## Functional flow

- New student: `/register` -> Supabase `signUp` -> **Confirm sign up** email containing six digits -> `/verify-email` -> `verifyOtp({email, token, type:"signup"})` -> verified session -> dashboard. Existing students continue to use passwords.
- Existing student passwordless login: `/login` -> **Email me a six-digit code** -> `signInWithOtp` with `shouldCreateUser:false` -> **Magic Link** template numeric code -> `/login/code` -> `verifyOtp({email, token, type:"email"})` -> verified session -> requested internal page. It cannot sign up an unregistered email.
- Codes are numeric exactly six digits. The server rejects incorrect, expired, or missing-session OTP responses. No account-existence details are displayed for unknown emails. Do not return OTPs in URLs, logs, or responses.

## Required end-to-end acceptance before production release

On staging, create a synthetic student with a **controlled test inbox** and use a genuine Supabase signup (do not fake email dispatch). Confirm one **six-digit numeric token** appears in the received message. Enter that code once and confirm authenticated dashboard access; verify re-use fails. Log out, request a separate six-digit **sign-in** code, and verify it through `/login/code`. Check resend, expiration, unknown email handling, rate limiting and email/password login regression.

Verify the **inbox receipt**, not merely an API success or an SMTP accepted response. After staging acceptance and passing CI, promote the front end through its release process and repeat a labelled production test using an authorized controlled test account and inbox. No real student account, existing payment or private record needs to be changed to complete this feature.

Official docs: https://supabase.com/docs/guides/auth/auth-email-templates and https://supabase.com/docs/guides/auth/auth-email-passwordless
