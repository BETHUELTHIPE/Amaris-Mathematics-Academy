from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from content.models import Enrollment, Payment, PaymentReconciliationRun


def reconcile_verified_payments() -> PaymentReconciliationRun:
    """Repair enrolment linkage without ever deciding that a payment is paid.

    Only records already marked paid by the verified gateway notification path,
    and carrying an explicit verification timestamp, are eligible. This makes
    the operation retry-safe and prevents redirects or client state from
    granting access.
    """

    run = PaymentReconciliationRun.objects.create()
    try:
        eligible_ids = (
            Payment.objects.filter(
                status=Payment.Status.PAID,
                gateway_verified_at__isnull=False,
            )
            .filter(Q(enrollment__isnull=True) | Q(enrollment__status=Enrollment.Status.PENDING))
            .values_list("pk", flat=True)
            .iterator(chunk_size=200)
        )
        unresolved = Payment.objects.filter(
            status=Payment.Status.PAID,
            gateway_verified_at__isnull=True,
        ).count()
        repaired = 0
        scanned = 0

        for payment_id in eligible_ids:
            with transaction.atomic():
                payment = (
                    Payment.objects.select_for_update(skip_locked=True, of=("self",))
                    .select_related("enrollment")
                    .filter(
                        pk=payment_id,
                        status=Payment.Status.PAID,
                        gateway_verified_at__isnull=False,
                    )
                    .first()
                )
                if payment is None:
                    continue
                scanned += 1
                enrollment, created = Enrollment.objects.select_for_update().get_or_create(
                    student=payment.student,
                    course=payment.course,
                    defaults={"status": Enrollment.Status.ACTIVE},
                )

                if enrollment.status == Enrollment.Status.CANCELLED:
                    unresolved += 1
                    continue

                changed = created
                if enrollment.status == Enrollment.Status.PENDING:
                    enrollment.status = Enrollment.Status.ACTIVE
                    enrollment.save(update_fields=["status", "updated_at"])
                    changed = True

                if payment.enrollment_id != enrollment.pk:
                    payment.enrollment = enrollment
                    payment.save(update_fields=["enrollment", "updated_at"])
                    changed = True

                if changed:
                    repaired += 1

        run.status = PaymentReconciliationRun.Status.SUCCEEDED
        run.completed_at = timezone.now()
        run.payments_scanned = scanned
        run.enrollments_repaired = repaired
        run.unresolved_count = unresolved
        run.save(
            update_fields=[
                "status",
                "completed_at",
                "payments_scanned",
                "enrollments_repaired",
                "unresolved_count",
                "updated_at",
            ]
        )
        return run
    except Exception as exc:
        run.status = PaymentReconciliationRun.Status.FAILED
        run.completed_at = timezone.now()
        run.error_code = exc.__class__.__name__[:120]
        run.save(update_fields=["status", "completed_at", "error_code", "updated_at"])
        raise
