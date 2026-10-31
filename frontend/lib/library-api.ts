import "server-only";
import { env } from "cloudflare:workers";
import { normalizeCmsApiBaseUrl } from "@/lib/cms-api-url";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export type LibraryRole = "student" | "tutor";
export type LibraryResource = {
  id: string; title: string; description: string;
  resource_type: "textbook" | "worksheet" | "notes" | "other";
  subject: string; level: string; original_name: string; size_bytes: number;
  content_type: string; is_published: boolean; created_at: string; can_manage: boolean;
};
export type LibraryPage = { results: LibraryResource[]; count: number; page: number; page_size: number };
export class LibraryError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export async function libraryToken(): Promise<string> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user?.email_confirmed_at) throw new LibraryError(401, "Sign in with a verified account to use the Library.");
  const session = await supabase.auth.getSession();
  const token = session.data.session?.access_token;
  if (!token) throw new LibraryError(401, "Your session expired. Please sign in again.");
  return token;
}
export async function libraryRequest(role: LibraryRole, path = "", init: RequestInit = {}, token?: string): Promise<Response> {
  const accessToken = token ?? await libraryToken();
  const bindings = env as unknown as { CMS_API_URL?: string };
  const base = bindings.CMS_API_URL || process.env.CMS_API_URL;
  if (!base) throw new LibraryError(503, "The Library is temporarily unavailable.");
  try {
    return await fetch(`${normalizeCmsApiBaseUrl(base)}/${role}/library/${path}`, {
      ...init,
      headers: { ...init.headers, Accept: "application/json", Authorization: `Bearer ${accessToken}` },
      cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(init.method === "POST" ? 90_000 : 12_000),
    });
  } catch {
    throw new LibraryError(503, "The Library could not confirm this request. Refresh the page before retrying an upload.");
  }
}
export async function getLibrary(role: LibraryRole, query: { q?: string; resource_type?: string; page?: string }): Promise<LibraryPage> {
  const params = new URLSearchParams();
  params.set("q", (query.q ?? "").slice(0, 150));
  params.set("resource_type", (query.resource_type ?? "").slice(0, 20));
  params.set("page", /^\d{1,6}$/.test(query.page ?? "") ? query.page! : "1");
  const response = await libraryRequest(role, `?${params}`);
  if (!response.ok) throw new LibraryError(response.status, [401, 403].includes(response.status)
    ? "Tutor access requires a verified account approved by an academy administrator."
    : "The Library is temporarily unavailable. Please try again shortly.");
  return response.json() as Promise<LibraryPage>;
}
