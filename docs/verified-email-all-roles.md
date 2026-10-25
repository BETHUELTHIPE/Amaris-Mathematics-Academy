# Amaris verified-email requirement for all website accounts

## Universal security requirement

Every registered Amaris website identity must **verify ownership of its email address before successfully signing in or entering private areas**, regardless of future account type (student, tutor applicant, approved tutor, sponsor, partner, contributor or staff website account).

- Email/password signup requests Supabase email confirmation; an unconfirmed account receives **no private dashboard access**.
- Email/password login performs an additional server-side `supabase.auth.getUser()` verification **after** Supabase accepts credentials. If `email_confirmed_at` is missing or the Auth service is unavailable, the session is locally signed out and the person is redirected to the correct email verification page.
- Tutor applicants provide a six-digit signup code or use the verification link, and must have both an authenticated session and confirmed email before they can submit private qualifications. The academy independently approves Tutors permission group membership before teaching privileges.
- Approved tutors, students and all other logged-in website roles share this requirement. The Django REST API separately validates email confirmation and authorizes permissions.
- Google sign-in callback rejects unconfirmed accounts and clears their local session. Email confirmation links and recovery links also verify the account server-side before redirecting into private pages.
- Supabase six-digit email OTP sign-in already requires a confirmed, authenticated user, and never creates a new account merely from a sign-in request.
- Existing verified website accounts remain usable. Do not overwrite or mass-confirm unverified users, disable email confirmations, or disclose whether an email exists through a registration or resend response.

## User experience

Registration → branded verification email (six-digit code and secure link) → confirmation → sign-in → **role-specific approval or checks** → permitted dashboard. Unconfirmed users see a verification link and can request a replacement confirmation code. Session, email and tokens must never be included in public logs or analytics.

## Current scope

The public **Support Our Project** page permits sponsors and donors to **enquire** using the contact form; it is not a sponsor account-registration or login portal and does not collect contributions. Public enquiries must not be treated as logged-in sponsor accounts. Any future sponsor/partner portal must route through this **same verified Supabase account gate** before its first private session, then apply sponsor/partner authorization.

Django Admin is a **separate staff authentication system**. Do not change or lock existing Django superuser access as part of the public website release; staff onboarding and multi-factor auth require a separately reviewed Django Admin control change.

## Acceptance tests

- New registered student and tutor applicant cannot access their private pages before confirming the email; six-digit code and signed link both work.
- Correct password, OAuth callback, or valid recovery link never substitutes for an unconfirmed email.
- Missing user, invalid/expired token, and Supabase Auth outages fail closed.
- Verified existing student and tutor accounts continue to sign in; tutor requests still require admin-approved permissions.
- Future sponsor/partner private accounts must pass these tests before a sponsor portal is introduced.
- Verify staging browser flows, protected endpoints, session handling and email inbox delivery before changing production.
