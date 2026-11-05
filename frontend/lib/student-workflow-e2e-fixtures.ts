/**
 * Fake students and completed activities for the local-only Playwright visual gate.
 * Never include real records, credentials, live payments or privileged Airflow data.
 * Imported only when the non-production synthetic E2E switch is enabled.
 */
import type { StudentCourse, StudentOrder } from "./student-api";

export const visualTestCourses: StudentCourse[] = [
  {
    course: {
      slug: "caps-grade-12-mathematics",
      title: "CAPS Grade 12 Mathematics — synthetic visual test",
      first_lesson_slug: "algebra",
    },
    resume: {
      course_slug: "caps-grade-12-mathematics",
      enrollment_status: "active",
      progress_percent: 63,
      last_position_seconds: 120,
      last_lesson: { id: 101, slug: "algebra", title: "Algebra foundations", module: "Algebra" },
      progress_updated_at: "2026-10-16T06:00:00+02:00",
    },
  },
];

const base = {
  amount: "250.00",
  currency: "ZAR",
  created_at: "2026-10-16T06:00:00+02:00",
  paid_at: "2026-10-16T06:05:00+02:00",
  invoice_number: null,
  invoice_ready: false,
};

export const visualTestOrders: StudentOrder[] = [
  {
    ...base,
    kind: "course",
    reference: "TEST-COURSE-001",
    title: "CAPS Grade 12 Mathematics — synthetic visual test",
    detail: "Verified test course enrollment",
    status: "paid",
    status_label: "Paid",
    href: "/courses/caps-grade-12-mathematics",
  },
  {
    ...base,
    kind: "live_class",
    reference: "TEST-CLASS-001",
    title: "Zoom Algebra Class — synthetic visual test",
    detail: "Verified test class booking",
    status: "confirmed",
    status_label: "Confirmed",
    href: "/book-online-live-class/confirmation?reference=TEST-CLASS-001",
  },
  {
    ...base,
    kind: "video_request",
    reference: "TEST-VIDEO-001",
    title: "Trigonometry video — synthetic visual test",
    detail: "Test tutor workflow undergoing review",
    status: "review",
    status_label: "Quality review",
    href: "/request-a-video/confirmation?reference=TEST-VIDEO-001",
  },
  {
    ...base,
    kind: "video_request",
    reference: "TEST-VIDEO-002",
    title: "Functions video — synthetic visual test",
    detail: "Test private lesson ready",
    status: "ready",
    status_label: "Ready",
    href: "/request-a-video/confirmation?reference=TEST-VIDEO-002",
  },
];
