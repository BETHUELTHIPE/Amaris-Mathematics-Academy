import "server-only";
import { cache } from "react";

import { env } from "cloudflare:workers";
import { normalizeCmsApiBaseUrl } from "@/lib/cms-api-url";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export type TutorSlot = {
  id: number;
  programme: "caps" | "ieb" | "tvet" | "university";
  subject: "mathematics" | "mathematical_literacy";
  level: string;
  starts_at: string;
  ends_at: string;
  duration_hours: number;
  zoom_join_url: string;
  is_active: boolean;
  price: string;
  reserved: boolean;
  editable: boolean;
};

export type TutorBooking = {
  reference: string;
  status: string;
  topic: string;
  programme: string;
  subject: string;
  level: string;
  starts_at: string;
  ends_at: string;
  duration_hours: number;
  amount: string;
  student_name: string;
  student_email: string;
  zoom_join_url: string;
};

export type TutorDashboard = {
  tutor: { name: string; email: string };
  rate_per_hour: string;
  max_hours: number;
  slots: TutorSlot[];
  bookings: TutorBooking[];
  summary: { upcoming_slots: number; confirmed_classes: number };
};

export class TutorApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "TutorApiError";
  }
}

// Cache only the tutor's verified token within one React server request.
// Django enforces tutor ownership on every subsequent no-store API request.
const verifiedTutorToken = cache(async () => {
  const supabase = await createSupabaseServerClient();
  // getUser revalidates with Supabase Auth. Never accept an unverified, client-supplied role.
  const { data: userData, error: userError } = await supabase.auth.getUser();
  if (userError || !userData.user || !userData.user.email_confirmed_at) {
    throw new TutorApiError(401, "Sign in with a verified tutor account.");
  }
  const { data: sessionData, error: sessionError } = await supabase.auth.getSession();
  const token = sessionData.session?.access_token;
  if (sessionError || !token) throw new TutorApiError(401, "Your tutor session has expired.");
  return token;
});

export async function tutorFetch<T>(
  path: string,
  method: "GET" | "POST" | "PATCH" = "GET",
  data?: Record<string, unknown>,
): Promise<T> {
  const token = await verifiedTutorToken();

  const bindings = env as unknown as { CMS_API_URL?: string };
  const configured = bindings.CMS_API_URL || process.env.CMS_API_URL;
  if (!configured) throw new TutorApiError(503, "Tutor services are temporarily unavailable.");
  const base = normalizeCmsApiBaseUrl(configured);
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      method,
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
        ...(data ? { "Content-Type": "application/json" } : {}),
      },
      ...(data ? { body: JSON.stringify(data) } : {}),
      cache: "no-store",
      signal: AbortSignal.timeout(12_000),
    });
  } catch {
    throw new TutorApiError(503, "Tutor services are temporarily unavailable.");
  }
  if (!response.ok) {
    let message = response.status === 401 || response.status === 403
      ? "This account has not been approved as a tutor."
      : "Unable to save your tutor session. Check the details and try again.";
    if (response.status === 400) {
      const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail.slice(0, 250);
    }
    throw new TutorApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export function getTutorDashboard(): Promise<TutorDashboard> {
  return tutorFetch<TutorDashboard>("/tutor/dashboard/");
}

export type TutorEarnings = {
  currency: "ZAR";
  categories: Record<"course" | "live_class" | "video", {
    count: number; students: number; gross: string; earned: string;
  }>;
  unique_students: number;
  total: string;
  paid_out: string;
  outstanding: string;
  classes_attended: number;
  bank_account_mask: string;
  recipient_verified: boolean;
};

export function getTutorEarnings(): Promise<TutorEarnings> {
  return tutorFetch<TutorEarnings>("/tutor/earnings/");
}

export type SlotInput = {
  programme?: string;
  subject?: string;
  level?: string;
  starts_at?: string;
  duration_hours?: number;
  zoom_join_url?: string;
  is_active?: boolean;
};

export function createTutorSlot(input: SlotInput): Promise<TutorSlot> {
  return tutorFetch<TutorSlot>("/tutor/slots/", "POST", input);
}

export function updateTutorSlot(id: number, input: SlotInput): Promise<TutorSlot> {
  return tutorFetch<TutorSlot>(`/tutor/slots/${id}/`, "PATCH", input);
}
