# Payment testing contract

Payments are treated as a critical backend-controlled boundary.

## Safety

- Automated tests never create a live charge and never call live PayFast.
- Checkout tests use the PayFast sandbox URL and a deterministic in-process verification adapter.
- Synthetic students, courses, references and gateway transaction IDs are used throughout.
- Browser redirects and client-supplied success flags never grant course access.

## Authoritative success path

A payment may activate a service only after the backend verifies a PayFast notification and rechecks the callback against server-owned payment facts:

1. the local payment reference already exists;
2. PayFast verification succeeds server-side;
3. the callback amount equals the amount stored by the server;
4. the student identifier matches the payment's student;
5. the service/course identifier matches the payment's course;
6. the callback is processed inside a database transaction;
7. the payment is marked paid and gateway-verified;
8. the enrollment/service is activated;
9. exactly one invoice is created;
10. exactly one service ticket is created;
11. exactly one durable payment-success notification is placed in the database outbox.

If fulfilment fails, the transaction rolls back the paid state and all service artifacts together.

## Idempotency

Checkout references are unique. Enrollment already has a unique student/course constraint. Invoice, service ticket and success-notification records are one-to-one with a payment. PayFast transaction/status webhook records are uniquely constrained so duplicate or replayed processed callbacks cannot create duplicate fulfilment artifacts.

## Covered scenarios

`content.test_payments` covers checkout creation and idempotency, pending, successful, failed and cancelled payments, duplicate callbacks, invalid callbacks, tampered amounts, wrong students, wrong services, replayed webhooks, verification timeouts, retries, network failures, browser success claims and transactional rollback.

The existing reconciliation tests remain separate: reconciliation may repair service linkage only for records that were already marked paid by a server-verified gateway path; reconciliation never decides that a payment succeeded.

## CI enforcement

The `Payment tests` quality gate runs both `content.tests.PaymentReconciliationTests` and `content.test_payments` against the CI PostgreSQL database. The full Django regression suite runs afterward as an additional guard against cross-feature regressions. A payment gate failure blocks downstream image build and release jobs.
