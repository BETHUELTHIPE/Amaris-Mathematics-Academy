import { env } from "cloudflare:workers";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { requireVerifiedStudent } from "@/lib/auth";

declare const __E2E_SYNTHETIC_STUDENT__: boolean;

export type ResumeState = {
  course_slug: string;
  enrollment_status: string;
  progress_percent: number;
  last_position_seconds: number;
  last_lesson: null | {
    id: number;
    slug: string;
    title: string;
    module: string;
  };
  progress_updated_at: string | null;
};

export type StudentCourse = {
  course: { slug: string; title: string };
  resume: ResumeState;
};

export type CheckoutSession = {
  payment_reference: string;
  status: string;
  gateway_url: string;
  fields: Record<string, string>;
  course: { slug: string; title: string };
};

export type LiveClassCheckoutSession = {
  booking_reference: string;
  status: string;
  gateway_url: string;
  fields: Record<string, string>;
  booking: {
    programme: string;
    subject: string;
    level: string;
    topic: string;
    tutor: string;
    starts_at: string;
    ends_at: string;
    amount: string;
    currency: string;
  };
};

export type LiveClassBookingStatus = {
  booking_reference: string;
  status: string;
  programme: string;
  subject: string;
  level: string;
  topic: string;
  tutor: string;
  starts_at: string;
  ends_at: string;
  amount: string;
  currency: string;
  invoice_number: string | null;
  invoice_ready: boolean;
  zoom_join_url: string;
};

export type VideoRequestCheckoutSession = {
  request_reference: string;
  status: string;
  gateway_url: string;
  fields: Record<string, string>;
  request: {
    request_type: string;
    programme: string;
    subject: string;
    level: string;
    topic: string;
    preferred_duration_minutes: number;
    amount: string;
    currency: string;
  };
  document_upload_prefix: string;
};

export type StudentVideoRequest = {
  request_reference: string;
  ticket_number: string | null;
  status: string;
  status_label: string;
  request_type: string;
  request_type_label: string;
  programme: string;
  subject: string;
  level: string;
  topic: string;
  preferred_duration_minutes: number;
  amount: string;
  currency: string;
  tutor: string;
  requests_ahead: number | null;
  queue_position: number | null;
  estimated_ready_from: string | null;
  estimated_ready_to: string | null;
  invoice_number: string | null;
  invoice_ready: boolean;
  document_count: number;
  document_total_bytes: number;
  document_upload_prefix: string;
  video: null | {
    provider: "youtube" | "direct";
    youtube_video_id: string;
    direct_download_url: string;
  };
};

export type ProtectedLesson = {
  course_slug: string;
  course_title: string;
  lesson: {
    id: number;
    slug: string;
    title: string;
    summary: string;
    lesson_body: string;
    duration_minutes: number;
    module: string;
    video: null | {
      provider: string;
      youtube_video_id: string;
      duration_seconds: number;
    };
  };
  resume: ResumeState;
};

function cmsBaseUrl(): string {
  const workerBindings = env as unknown as { CMS_API_URL?: string };
  const base = (workerBindings.CMS_API_URL || process.env.CMS_API_URL)?.replace(/\/$/, "");
  if (!base) throw new Error("The protected student API is not configured.");
  return base;
}

async function accessToken(): Promise<string> {
  await requireVerifiedStudent();
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (error || !token) throw new Error("Your student session has expired. Please log in again.");
  return token;
}

async function studentFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await accessToken();
  const response = await fetch(`${cmsBaseUrl()}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
    cache: "no-store",
    signal: AbortSignal.timeout(8_000),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Student API request failed (${response.status}): ${body.slice(0, 180)}`);
  }
  return response.json() as Promise<T>;
}

async function checkoutKey(courseSlug: string): Promise<string> {
  const student = await requireVerifiedStudent();
  const bytes = new TextEncoder().encode(`${student.id}:${courseSlug}`);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return `checkout-${Array.from(new Uint8Array(digest)).slice(0, 20).map((value) => value.toString(16).padStart(2, "0")).join("")}`;
}

export async function createStudentCheckout(courseSlug: string): Promise<CheckoutSession> {
  return studentFetch<CheckoutSession>("/student/checkout/", {
    method: "POST",
    body: JSON.stringify({
      course_slug: courseSlug,
      idempotency_key: await checkoutKey(courseSlug),
    }),
  });
}

async function liveClassCheckoutKey(slotId: string, topic: string, attempt: string): Promise<string> {
  const student = await requireVerifiedStudent();
  const normalizedTopic = topic.trim().replace(/\s+/g, " ").toLowerCase();
  const bytes = new TextEncoder().encode(`${student.id}:${slotId}:${normalizedTopic}:${attempt}`);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const hex = Array.from(new Uint8Array(digest))
    .slice(0, 20)
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
  return `liveclass-${hex}`;
}

export async function createStudentLiveClassCheckout(
  slotId: string,
  topic: string,
  attempt: string,
): Promise<LiveClassCheckoutSession> {
  return studentFetch<LiveClassCheckoutSession>("/student/live-classes/checkout/", {
    method: "POST",
    body: JSON.stringify({
      slot_id: slotId,
      topic: topic.trim(),
      idempotency_key: await liveClassCheckoutKey(slotId, topic, attempt),
    }),
  });
}

export async function getStudentLiveClassBooking(
  reference: string,
): Promise<LiveClassBookingStatus> {
  return studentFetch<LiveClassBookingStatus>(
    `/student/live-classes/bookings/${encodeURIComponent(reference)}/`,
  );
}

export async function createStudentVideoRequestCheckout(
  formData: FormData,
): Promise<VideoRequestCheckoutSession> {
  const token = await accessToken();
  const response = await fetch(`${cmsBaseUrl()}/student/video-requests/checkout/`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: formData,
    cache: "no-store",
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Video request failed (${response.status}): ${body.slice(0, 240)}`);
  }
  return response.json() as Promise<VideoRequestCheckoutSession>;
}

export async function registerStudentVideoDocument(input: {
  request_reference: string;
  storage_path: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
}): Promise<{ id: number; size_bytes: number }> {
  const { request_reference, ...metadata } = input;
  if (!/^VRQ-[A-Za-z0-9_-]{8,64}$/.test(request_reference)) {
    throw new Error("Invalid video request reference.");
  }
  return studentFetch<{ id: number; size_bytes: number }>(
    `/student/video-requests/${encodeURIComponent(request_reference)}/documents/`,
    { method: "POST", body: JSON.stringify(metadata) },
  );
}

export async function getStudentVideoRequests(): Promise<StudentVideoRequest[]> {
  if (__E2E_SYNTHETIC_STUDENT__) return [];
  return studentFetch<StudentVideoRequest[]>("/student/video-requests/");
}

export async function getStudentVideoRequest(reference: string): Promise<StudentVideoRequest> {
  return studentFetch<StudentVideoRequest>(
    `/student/video-requests/${encodeURIComponent(reference)}/`,
  );
}

export async function downloadStudentVideoRequestInvoice(reference: string): Promise<Response> {
  const token = await accessToken();
  return fetch(
    `${cmsBaseUrl()}/student/video-requests/${encodeURIComponent(reference)}/invoice/`,
    {
      headers: { Accept: "application/pdf", Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    },
  );
}

export async function streamStudentRequestedVideo(reference: string): Promise<Response> {
  const token = await accessToken();
  return fetch(
    `${cmsBaseUrl()}/student/video-requests/${encodeURIComponent(reference)}/video/`,
    {
      headers: { Accept: "video/mp4", Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    },
  );
}

export async function downloadStudentLiveClassInvoice(reference: string): Promise<Response> {
  const token = await accessToken();
  return fetch(
    `${cmsBaseUrl()}/student/live-classes/bookings/${encodeURIComponent(reference)}/invoice/`,
    {
      headers: { Accept: "application/pdf", Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    },
  );
}

export async function getStudentCourses(): Promise<StudentCourse[]> {
  if (__E2E_SYNTHETIC_STUDENT__) return [];
  return studentFetch<StudentCourse[]>("/student/courses/");
}

export async function getProtectedLesson(courseSlug: string, lessonSlug: string): Promise<ProtectedLesson> {
  return studentFetch<ProtectedLesson>(
    `/student/lessons/${encodeURIComponent(courseSlug)}/${encodeURIComponent(lessonSlug)}/`,
  );
}

export async function saveStudentProgress(input: {
  courseSlug: string;
  lessonSlug: string;
  positionSeconds: number;
  progressPercent?: number;
}): Promise<ResumeState> {
  return studentFetch<ResumeState>("/student/progress/", {
    method: "PATCH",
    body: JSON.stringify({
      course_slug: input.courseSlug,
      lesson_slug: input.lessonSlug,
      position_seconds: input.positionSeconds,
      ...(typeof input.progressPercent === "number" ? { progress_percent: input.progressPercent } : {}),
    }),
  });
}
