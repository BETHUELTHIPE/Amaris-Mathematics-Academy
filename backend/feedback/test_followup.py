from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from content.models import StudentRecord
from feedback.followup import create_followup_for_form
from feedback.models import FeedbackFollowUp, HappyForm


class LowRatingFollowupTests(TestCase):
    def setUp(self):
        self.student = StudentRecord.objects.create(
            email="followup-test@example.test",
            supabase_user_id="00000000-0000-4000-8000-000000000119",
        )

    def make_form(self, *, overall, tutor=None, reference="service-1"):
        return HappyForm.objects.create(
            student=self.student,
            service=HappyForm.Service.LIVE_CLASS,
            service_reference=reference,
            service_title="Algebra class",
            overall_rating=overall,
            tutor_rating=tutor,
        )

    @patch("feedback.tasks.notify_new_followup.delay")
    def test_low_service_rating_opens_one_followup_due_in_two_days(self, notify):
        with self.captureOnCommitCallbacks(execute=True):
            form = self.make_form(overall=2)
            first = create_followup_for_form(form)
            second = create_followup_for_form(form)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(FeedbackFollowUp.objects.count(), 1)
        self.assertAlmostEqual(
            (first.due_at - form.created_at).total_seconds(),
            timedelta(days=2).total_seconds(),
            delta=1,
        )
        notify.assert_called_once_with(first.pk)

    @patch("feedback.tasks.notify_new_followup.delay")
    def test_low_tutor_rating_also_opens_followup(self, notify):
        with self.captureOnCommitCallbacks(execute=True):
            form = self.make_form(overall=5, tutor=1)
            create_followup_for_form(form)
        self.assertTrue(FeedbackFollowUp.objects.filter(feedback=form).exists())
        notify.assert_called_once()

    @patch("feedback.tasks.notify_new_followup.delay")
    def test_positive_rating_does_not_open_followup(self, notify):
        form = self.make_form(overall=5, tutor=4)
        self.assertIsNone(create_followup_for_form(form))
        notify.assert_not_called()
