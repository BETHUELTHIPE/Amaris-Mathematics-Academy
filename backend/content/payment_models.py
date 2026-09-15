from django.db import models

from .models import Course, Enrollment, Payment, StudentRecord, TimeStampedModel


class PaymentWebhookEvent(TimeStampedModel):
    class State(models.TextChoices):
        RECEIVED = "received", "Received"
        RETRYABLE = "retryable", "Retryable"
        PROCESSED = "processed", "Processed"
        REJECTED = "rejected", "Rejected"

    provider = models.CharField(max_length=16, default=Payment.Provider.PAYFAST)
    provider_reference = models.CharField(max_length=160)
    payment_status = models.CharField(max_length=32)
    local_reference = models.CharField(max_length=100)
    payment = models.ForeignKey(
        Payment,
        related_name="webhook_events",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )
    payload_hash = models.CharField(max_length=64, blank=True, editable=False)
    state = models.CharField(max_length=16, choices=State.choices, default=State.RECEIVED, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error_code = models.CharField(max_length=80, blank=True, editable=False)
    verified_at = models.DateTimeField(blank=True, null=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "provider_reference", "payment_status"),
                name="pay_webhook_provider_status_unique",
            )
        ]
        indexes = [
            models.Index(fields=("state", "-created_at"), name="pay_webhook_state_time_idx"),
            models.Index(fields=("local_reference",), name="pay_webhook_local_ref_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.provider_reference} — {self.payment_status}"


class Invoice(TimeStampedModel):
    payment = models.OneToOneField(Payment, related_name="invoice", on_delete=models.PROTECT)
    invoice_number = models.CharField(max_length=120, unique=True)
    student = models.ForeignKey(StudentRecord, related_name="invoices", on_delete=models.PROTECT)
    course = models.ForeignKey(Course, related_name="invoices", on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="ZAR")
    issued_at = models.DateTimeField()

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self) -> str:
        return self.invoice_number


class ServiceTicket(TimeStampedModel):
    class Status(models.TextChoices):
        FULFILLED = "fulfilled", "Fulfilled"

    payment = models.OneToOneField(Payment, related_name="service_ticket", on_delete=models.PROTECT)
    enrollment = models.ForeignKey(Enrollment, related_name="service_tickets", on_delete=models.PROTECT)
    ticket_number = models.CharField(max_length=120, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.FULFILLED, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.ticket_number


class NotificationOutbox(TimeStampedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    payment = models.OneToOneField(Payment, related_name="success_notification", on_delete=models.PROTECT)
    event_type = models.CharField(max_length=40, default="payment_success")
    destination = models.EmailField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED, db_index=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=("status", "created_at"), name="notify_outbox_status_idx")]

    def __str__(self) -> str:
        return f"{self.event_type} — {self.payment.reference}"
