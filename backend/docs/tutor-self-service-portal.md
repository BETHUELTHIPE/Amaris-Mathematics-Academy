# Amaris Tutor Self-Service Portal

The Tutor Portal is available at `/tutor/login` on the student web application.
It uses the existing Supabase login and the Django PostgreSQL `auth_user` / `auth_group` tables. **No automatic tutor role is assigned by public registration.**

## Approving a tutor (Super Admin only)

1. In Django Admin open **Authentication and Authorization → Groups**.
2. Create a group with the exact name **Tutors**, if it does not yet exist.
3. Open **Users** and create or locate the tutor's Django user. The email must match their **verified Supabase Auth account email** exactly (case-insensitive).
4. Do **not** mark the user as a Django superuser. Normal tutors need neither `is_staff` nor `is_superuser`. Do not reuse the academy's superadmin account.
5. Add the user to the **Tutors** group, ensure `is_active=True`, save. Avoid duplicate Tutor group members with the same email.
6. Have the tutor sign in to the student site at `/tutor/login` with their existing verified Supabase account (email/password or Google). They will reach `/tutor/dashboard`.

For new tutor-only Django records, set an unusable Django password with `set_unusable_password()` when provisioning through approved admin tooling; tutor authentication is via Supabase only.

## Portal capabilities

- Create, list, edit, pause and republish *unbooked future* slots with 1–24 whole hours, programme, subject, level, start time and a private Zoom meeting link.
- View own pending and confirmed sessions, booking statuses, topic, start time, duration and hourly totals.
- See student contact details and the Zoom launch button **only for verified confirmed/completed bookings**.
- Cannot view another tutor's records, grant their own role, set prices, approve payments, or modify reserved/paid/past sessions.
- Booking fees are always calculated on the backend at R250 per selected hour. No real money is collected from the tutor management forms.

The private Django endpoints are `GET /api/v1/tutor/dashboard/`, `POST /api/v1/tutor/slots/` and `PATCH /api/v1/tutor/slots/<id>/`. They require a verified Supabase Bearer token and the tutor's exact approved group membership. The frontend invokes them on the server through Supabase HTTP-only session cookies, not from browser JavaScript.

## Production acceptance

Run the isolated `content.test_tutor_dashboard` suite and the normal CI release gates. Use two synthetic tutor identities to test ownership isolation. Check 1h / 2h / 3h amounts (R250 / R500 / R750), overlap rejection, reserved-session locks, no Zoom leaks and email-verification requirements. Check web accessibility and mobile layouts. Do not create real bookings or payments during release verification.

The academy should confirm its Zoom host license allows the selected session duration. Zoom meetings are not created automatically by this portal; tutors supply their own valid meeting link. A separate host-integrated meeting creation flow would require additional Zoom permissions and appropriate licensing.
