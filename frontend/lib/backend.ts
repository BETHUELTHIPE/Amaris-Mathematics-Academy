import "server-only";

import { createSupabaseServerClient } from "@/lib/supabase/server";
import { readEnvironmentValue } from "@/lib/supabase/config";

const backendBaseUrl = readEnvironmentValue("CMS_API_URL")?.replace(/\/$/, "");

export class BackendRequestError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "BackendRequestError";
    this.status = status;
  }
}

async function getAccessToken(): Promise<string> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (error || !token) {
    throw new BackendRequestError(401, "Your student session has expired.");
  }
  return token;
}

export async function studentApi<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  if (!backendBaseUrl) {
    throw new BackendRequestError(503, "The learning service is temporarily unavailable.");
  }

  const token = await getAccessToken();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${backendBaseUrl}${path}`, {
    ...init,
    headers,
    cache: "no-store",
    signal: AbortSignal.timeout(8_000),
  });

  let payload: unknown = null;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    payload = await response.json();
  }

  if (!response.ok) {
    const detail =
      payload &&
      typeof payload === "object" &&
      "detail" in payload &&
      typeof (payload as { detail?: unknown }).detail === "string"
        ? (payload as { detail: string }).detail
        : "The learning service could not complete this request.";
    throw new BackendRequestError(response.status, detail);
  }
  return payload as T;
}
