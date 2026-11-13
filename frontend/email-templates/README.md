# Company letterhead for hosted account emails

These three templates use the same company letterhead as the Django emails: academy logo/name, director, contacts, address, navy/gold design and footer. The six-digit code and existing confirmation/recovery links are preserved exactly.

| Supabase Auth template | File |
| --- | --- |
| Confirm signup | confirm-signup.html |
| Magic link | magic-link-login.html |
| Reset password | recovery.html |

These are reviewed source templates; merging frontend source does **not** update hosted Supabase Auth configuration. During an authorised rollout, inspect the intended staging project's current Auth templates, preserve its flow/redirect variables, save rollback copies and apply these bodies through the Auth email-template settings or authenticated Management API. The Supabase connector currently exposed to this session has no Auth configuration-write capability, so no hosted templates were changed.

Test one genuine synthetic signup, six-digit login and recovery in staging: expected recipient, branded rendering, unchanged code/link behaviour and successful verification/reset. Confirm that link-prefetching cannot consume recovery tokens before the intentional Continue action. Repeat the authorised production acceptance after applying the exact reviewed configuration. Never alter OTP length, expiry, redirect allowlists or rate limits just for branding.

Hosted Auth templates use the existing HTTPS public brand logo; private CMS objects must not be made public. Unlike Django email, hosted template settings cannot attach the inline MIME logo. Text identity/contacts remain visible if an email client blocks images. Check the public logo endpoint during deployment.

Other hosted provider templates (if enabled later, such as invitations or email-address changes) must receive the same letterhead as part of enabling that provider flow. They are not represented by these three source files. No real account or email changed during these source tests.
