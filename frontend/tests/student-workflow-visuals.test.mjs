import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { studentWorkflow } from "../lib/student-workflow-states.ts";

const order = (kind, status) => ({
  kind,
  reference: "synthetic-order-1",
  title: "Synthetic test activity",
  detail: "Synthetic only",
  amount: "250.00",
  currency: "ZAR",
  status,
  status_label: status,
  created_at: "2026-10-16T08:00:00+02:00",
  paid_at: null,
  invoice_number: null,
  invoice_ready: false,
  href: "/dashboard/orders",
});

test("video milestones never imply processing completed before the corresponding state", () => {
  const expected = {
    pending_payment: 1,
    queued: 2,
    tutor_assigned: 3,
    recording: 3,
    processing: 4,
    review: 5,
    ready: 7,
  };
  for (const [status, confirmed] of Object.entries(expected)) {
    const workflow = studentWorkflow(order("video_request", status));
    assert.equal(workflow.confirmedCount, confirmed, status);
    assert.equal(workflow.totalCount, 7);
    assert.equal(workflow.milestones.filter((item) => item.state === "complete").length, confirmed);
  }
});

test("unpaid or disputed activities do not appear as completed", () => {
  for (const kind of ["course", "live_class", "video_request"]) {
    const review = studentWorkflow(order(kind, "payment_review"));
    assert.equal(review.confirmedCount, 1);
    assert.equal(review.attention, true);
    assert.equal(review.milestones[1].state, "attention");
    const cancelled = studentWorkflow(order(kind, "cancelled"));
    assert.equal(cancelled.confirmedCount, 1);
    assert.equal(cancelled.attention, true);
  }
});

test("confirmed and completed live classes are distinct states", () => {
  assert.equal(studentWorkflow(order("live_class", "pending_payment")).confirmedCount, 1);
  assert.equal(studentWorkflow(order("live_class", "confirmed")).confirmedCount, 3);
  assert.equal(studentWorkflow(order("live_class", "completed")).confirmedCount, 4);
  assert.equal(studentWorkflow(order("live_class", "expired")).milestones[1].state, "attention");
});

test("course unlock is not claimed without enrollment from the student's own account", () => {
  assert.equal(studentWorkflow(order("course", "paid"), false).confirmedCount, 2);
  assert.equal(studentWorkflow(order("course", "paid"), true).confirmedCount, 3);
  assert.equal(studentWorkflow(order("course", "pending"), true).confirmedCount, 1);
  assert.equal(studentWorkflow(order("course", "refunded"), true).confirmedCount, 1);
});

test("new dashboard component relies on student-owned API without Airflow secrets or Grafana embedding", async () => {
  const base = new URL("../", import.meta.url);
  const page = await readFile(new URL("./app/dashboard/page.tsx", base), "utf8");
  const visual = await readFile(new URL("./components/site/student-workflow-visuals.tsx", base), "utf8");
  const navigation = await readFile(new URL("./components/site/dashboard-navigation.tsx", base), "utf8");
  const refresh = await readFile(new URL("./components/site/student-workflow-refresh.tsx", base), "utf8");
  assert.match(page, /requireVerifiedStudent\("\/dashboard"\)/);
  assert.match(page, /getStudentOrders\(\)/);
  assert.match(page, /Promise\.allSettled\(/);
  assert.match(page, /<StudentWorkflowVisuals/);
  assert.match(visual, /studentWorkflow\(order, coursesAvailable/);
  assert.match(visual, /ordersAvailable/);
  assert.match(visual, /temporarily unavailable/);
  assert.match(visual, /aria-label=\{"Progress for "/);
  assert.match(navigation, /label: "My workflows", href: "\/dashboard#my-workflows"/);
  assert.match(refresh, /router\.refresh\(\)/);
  assert.match(refresh, /aria-label="Refresh my workflow progress"/);
  assert.doesNotMatch(page + visual, /AIRFLOW_API_TOKEN|\/api\/v2\/dags|iframe|supabase\.service_role|GRAFANA_API_KEY/);
});

test("synthetic workflow records are impossible in the Render production build", async () => {
  const localConfig = await readFile(new URL("../vite.config.ts", import.meta.url), "utf8");
  const productionConfig = await readFile(new URL("../vite.node.config.ts", import.meta.url), "utf8");
  const api = await readFile(new URL("../lib/student-api.ts", import.meta.url), "utf8");
  assert.match(localConfig, /syntheticE2EStudent && process\.env\.E2E_WORKFLOW_FIXTURES === "true"/);
  assert.match(productionConfig, /__E2E_SYNTHETIC_STUDENT__: JSON\.stringify\(false\)/);
  assert.match(productionConfig, /__E2E_SYNTHETIC_WORKFLOWS__: JSON\.stringify\(false\)/);
  assert.match(api, /if \(__E2E_SYNTHETIC_STUDENT__\) return __E2E_SYNTHETIC_WORKFLOWS__ \? visualTestOrders : \[\]/);
});
