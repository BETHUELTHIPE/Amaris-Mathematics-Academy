# Amaris Mathematics Academy Security Summary

## Status

**NOT READY FOR PRODUCTION**

This status is intentionally conservative. The source-level production controls and automated OWASP-aligned gates are in place, but the complete payment, booking, upload, student-owned learning and live Supabase attack surface must be exercised in staging before a PASS can be issued.

## Current automated coverage

| Category | Status | Notes |
|---|---|---|
| SQL injection | PARTIAL | Public course search regression test added. Expand to every writable/filter endpoint as features are added. |
| XSS | PARTIAL | Reflected search regression test added. Stored XSS requires writable rich-text/profile endpoints. |
| CSRF | PARTIAL | Django CSRF middleware and secure cookie settings are enforced; staging session-auth checks remain. |
| Authentication | PARTIAL | Supabase signup, six-digit verification, login, recovery and logout contracts are automated; provider-enforced expiry, reuse and throttling require staging evidence. |
| Authorization | AUTOMATED | DRF is private by default, public views opt into AllowAny, Django RBAC is tested, and public signup cannot request privileged roles. |
| IDOR | BLOCKED | Requires student/tutor owned-object APIs. |
| Session security | PARTIAL | Production security setting assertions added. |
| Cookie security | PARTIAL | Secure production cookie assertions added. |
| Security headers | AUTOMATED | Django, NGINX and the Cloudflare worker enforce browser hardening headers; authenticated routes are private/no-store. |
| Open redirect | REVIEW | Add endpoint tests wherever redirect/callback parameters are introduced. |
| Path traversal | PARTIAL | Public URL regression test added; file download APIs need dedicated tests. |
| File uploads | BLOCKED | Requires upload endpoints. |
| Mass assignment | BLOCKED | Requires private writable serializers. |
| API authorization | REVIEW | Public content API audited at baseline; private API matrix required when those endpoints exist. |
| Information disclosure | PARTIAL | Error-response leakage regression checks added. |
| Debug leakage | PARTIAL | Production-like deploy check added. |
| Business logic | BLOCKED | Requires booking/payment/access APIs. |
| Rate limiting | PARTIAL | DRF throttles plus NGINX enquiry/admin-login rate limits are enforced; distributed staging exhaustion evidence remains. |
| Dependency audit | AUTOMATED | pip-audit and npm audit added to CI. |
| Secret scan | AUTOMATED | Gitleaks added to CI. |
| Container scan | AUTOMATED | Trivy HIGH/CRITICAL image gate added to CI. |

## Release gate

Production must remain blocked for confirmed authorization bypass, IDOR, authentication bypass, payment/access-control bypass, exposed secrets, critical injection, critical stored XSS, privilege escalation, or failed critical Django deployment checks.

## Next expansion

As private authentication, student, tutor, booking, invoice, payment, video-access, progress and upload APIs become available, add two-user/two-tutor object-level authorization fixtures and a complete endpoint/role matrix. Do not weaken tests to obtain a green build.
