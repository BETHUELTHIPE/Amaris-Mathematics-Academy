# Amaris Mathematics Academy Security Summary

## Status

**NOT READY FOR PRODUCTION**

This status is intentionally conservative. The automated OWASP-aligned security suite has been introduced, but the complete role-based authentication, payment, booking, upload, student, tutor, and super-admin attack surface must be present and exercised before a PASS can be issued.

## Current automated coverage

| Category | Status | Notes |
|---|---|---|
| SQL injection | PARTIAL | Public course search regression test added. Expand to every writable/filter endpoint as features are added. |
| XSS | PARTIAL | Reflected search regression test added. Stored XSS requires writable rich-text/profile endpoints. |
| CSRF | REVIEW | Django CSRF middleware/configuration must remain enabled; state-changing session-auth endpoints require dedicated tests. |
| Authentication | BLOCKED | Full application authentication endpoints were not identified in the current Django content API. |
| Authorization | REVIEW | Global DRF default is currently AllowAny. Public content is intentional, but every future private API must explicitly set permissions. |
| IDOR | BLOCKED | Requires student/tutor owned-object APIs. |
| Session security | PARTIAL | Production security setting assertions added. |
| Cookie security | PARTIAL | Secure production cookie assertions added. |
| Security headers | PARTIAL | Django baseline assertions added; CSP/Permissions-Policy need frontend-specific validation. |
| Open redirect | REVIEW | Add endpoint tests wherever redirect/callback parameters are introduced. |
| Path traversal | PARTIAL | Public URL regression test added; file download APIs need dedicated tests. |
| File uploads | BLOCKED | Requires upload endpoints. |
| Mass assignment | BLOCKED | Requires private writable serializers. |
| API authorization | REVIEW | Public content API audited at baseline; private API matrix required when those endpoints exist. |
| Information disclosure | PARTIAL | Error-response leakage regression checks added. |
| Debug leakage | PARTIAL | Production-like deploy check added. |
| Business logic | BLOCKED | Requires booking/payment/access APIs. |
| Rate limiting | PARTIAL | Configuration assertion added; endpoint-specific exhaustion tests remain. |
| Dependency audit | AUTOMATED | pip-audit and npm audit added to CI. |
| Secret scan | AUTOMATED | Gitleaks added to CI. |
| Container scan | AUTOMATED | Trivy HIGH/CRITICAL image gate added to CI. |

## Release gate

Production must remain blocked for confirmed authorization bypass, IDOR, authentication bypass, payment/access-control bypass, exposed secrets, critical injection, critical stored XSS, privilege escalation, or failed critical Django deployment checks.

## Next expansion

As private authentication, student, tutor, booking, invoice, payment, video-access, progress and upload APIs become available, add two-user/two-tutor object-level authorization fixtures and a complete endpoint/role matrix. Do not weaken tests to obtain a green build.
