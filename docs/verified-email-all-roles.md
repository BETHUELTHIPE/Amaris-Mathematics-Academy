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

## Password reset and recovery applies to every registered website account

The **same** `/forgot-password` → `/reset-password/verify` → `/reset-password` flow is used for students, tutors, tutor applicants and any later registered sponsor/partner user. It is **not** a student-only password store. The Supabase Auth identity associated with the registered email address owns the password, independent of any academy role.

1. A user enters their registered email on the shared public recovery page. Never reveal whether the address belongs to an existing account.
2. Supabase sends the email's branded **six-digit recovery code** and secure reset link. The link opens a non-consuming page until the user actively confirms it; OTP redemption is verified on the server.
3. Only a successfully verified, email-confirmed account with a **15-minute cryptographically signed recovery proof bound to the current Supabase user and session** can set a strong new password. A normal signed-in session, forged `1` cookie, expired proof, stale session, or mismatched account must fail closed.
4. Password changes revoke authenticated sessions and clear the recovery marker. The user signs in again using the student, tutor or tutor-applicant login portal. A future sponsor portal must use the same Auth API and account check.
5. Password recovery **does not** grant Tutor-group membership, sponsor permissions or administrative access. Verification and role authorization are separate checks.

The public sponsor enquiry page still has no sponsor account portal. Django Admin credentials are managed separately from website Supabase Auth and must not be silently changed by public account-recovery work. Google-only accounts that want to set a password may use recovery for their verified email, without disabling Google's existing sign-in.

### Regression gate

Automated tests validate the same email recovery for student, tutor, applicant and hypothetical future sponsor identities; confirm the recovery token, required email confirmation, strong-password update, and global sign-out; test each existing login portal's Forgot password link, and reject missing or expired recovery proofs. Real SMTP inbox and browser acceptance should be repeated on staging before production deployment.

### Required deployment safeguard

The signed recovery proof requires an independent high-entropy `PASSWORD_RECOVERY_SIGNING_SECRET` (at least 43 random characters) configured as a **server-only Render environment secret**, independently for staging and production. Never commit its value, expose it as `NEXT_PUBLIC_*`, reuse a Supabase service-role token, or log it. If this value is absent or weak, password recovery must fail closed. Before production release, verify this variable is set securely in the existing Render student frontend and exercise fresh six-digit reset email → signed cookie → strong password save → global sign-out → new-password sign-in on staging. Retain previous production revision and rollback safeguards.
