/**
 * Student-safe presentation of verified Django order states.
 *
 * This is NOT the Apache Airflow DAG UI: never fetch or expose Airflow tokens,
 * operational task logs, other students' data, or speculative task states.
 */
import type { StudentOrder } from "./student-api";

export type Milestone = {
  label: string;
  state: "complete" | "current" | "upcoming" | "attention";
};

export type StudentWorkflow = {
  kind: StudentOrder["kind"];
  reference: string;
  title: string;
  detailHref: string;
  statusLabel: string;
  confirmedCount: number;
  totalCount: number;
  attention: boolean;
  milestones: Milestone[];
};

const VIDEO_PAID = new Set(["queued", "tutor_assigned", "recording", "processing", "review", "ready"]);
const VIDEO_ASSIGNED = new Set(["tutor_assigned", "recording", "processing", "review", "ready"]);
const VIDEO_RECORDING = new Set(["recording", "processing", "review", "ready"]);
const VIDEO_REVIEWED = new Set(["review", "ready"]);
const LIVE_CONFIRMED = new Set(["confirmed", "completed"]);
const ATTENTION = new Set(["failed", "cancelled", "expired", "refunded", "payment_review"]);

function stepsFor(order: StudentOrder, enrolled: boolean): { labels: string[]; confirmed: number } {
  const status = order.status.toLowerCase();

  if (order.kind === "video_request") {
    return {
      labels: ["Request received", "Payment verified", "Tutor assigned", "Video preparation", "Quality review", "Video ready"],
      confirmed: 1
        + Number(VIDEO_PAID.has(status))
        + Number(VIDEO_ASSIGNED.has(status))
        + Number(VIDEO_RECORDING.has(status))
        + Number(VIDEO_REVIEWED.has(status))
        + Number(status === "ready"),
    };
  }

  if (order.kind === "live_class") {
    return {
      labels: ["Booking requested", "Payment verified", "Class confirmed", "Class completed"],
      confirmed: 1 + 2 * Number(LIVE_CONFIRMED.has(status)) + Number(status === "completed"),
    };
  }

  const paymentVerified = status === "paid";
  return {
    labels: ["Order created", "Payment verified", "Course accessible"],
    confirmed: 1 + Number(paymentVerified) + Number(paymentVerified && enrolled),
  };
}

export function studentWorkflow(order: StudentOrder, enrolled = false): StudentWorkflow {
  const { labels, confirmed } = stepsFor(order, enrolled);
  const status = order.status.toLowerCase();
  const attention = ATTENTION.has(status);
  const milestones: Milestone[] = labels.map((label, index) => ({
    label,
    state: index < confirmed ? "complete"
      : index === confirmed ? (attention ? "attention" : "current")
      : "upcoming",
  }));
  return {
    kind: order.kind,
    reference: order.reference,
    title: order.title,
    detailHref: order.href,
    statusLabel: order.status_label || "Status not provided",
    confirmedCount: confirmed,
    totalCount: labels.length,
    attention,
    milestones,
  };
}
