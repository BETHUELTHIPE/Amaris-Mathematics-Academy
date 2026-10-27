import "server-only";

import { env } from "cloudflare:workers";
import { normalizeCmsApiBaseUrl } from "@/lib/cms-api-url";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export type TutorApplication = {
  reference: string;
  status: "submitted" | "reviewing" | "shortlisted" | "closed";
  submitted_at: string;
  acknowledgement_sent_at: string | null;
  documents: { id: string; category: "legacy" | "id" | "cv" | "matric" | "academic" | "tertiary" | "other"; original_name: string; size_bytes: number }[];
};
export class ApplicationError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function applicantToken(): Promise<string> {
  try {
    const supabase = await createSupabaseServerClient();
    const { data, error } = await supabase.auth.getUser();
    if (error || !data.user?.email_confirmed_at) throw new ApplicationError(401, "Sign in and verify your email before applying.");
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (!token) throw new ApplicationError(401, "Your session expired. Please sign in again.");
    return token;
  } catch (error) {
    if (error instanceof ApplicationError) throw error;
    throw new ApplicationError(503, "Account verification is temporarily unavailable. Please try again.");
  }
}

export async function applicationRequest(path = "", init: RequestInit = {}, token?: string): Promise<Response> {
  const accessToken = token ?? await applicantToken();
  const bindings = env as unknown as { CMS_API_URL?: string };
  const base = bindings.CMS_API_URL || process.env.CMS_API_URL;
  if (!base) throw new ApplicationError(503, "Applications are temporarily unavailable. Please try again shortly.");
  try {
    return await fetch(`${normalizeCmsApiBaseUrl(base)}/tutor-applications/${path}`, {
      ...init,
      headers: { Accept: "application/json", Authorization: `Bearer ${accessToken}` },
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    throw new ApplicationError(503, "The application service did not respond. Your form is still here; please retry.");
  }
}
