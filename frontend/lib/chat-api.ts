import "server-only";

import { env } from "cloudflare:workers";
import { getStudentIdentity } from "@/lib/auth";
import { normalizeCmsApiBaseUrl } from "@/lib/cms-api-url";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import type { ChatRooms } from "@/lib/chat";

export async function fetchChat(path: string, init: RequestInit = {}): Promise<Response> {
  try {
    const identity = await getStudentIdentity();
    if (!identity?.emailVerified) return new Response(null, { status: identity ? 403 : 401 });

    const supabase = await createSupabaseServerClient();
    const { data, error } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (error || !token) return new Response(null, { status: 401 });

    const bindings = env as unknown as { CMS_API_URL?: string };
    const url = bindings.CMS_API_URL || process.env.CMS_API_URL;
    if (!url) return new Response(null, { status: 503 });
    return await fetch(`${normalizeCmsApiBaseUrl(url)}/chat/rooms/${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
        ...(init.body ? { "Content-Type": "application/json" } : {}),
      },
      redirect: "error",
      signal: AbortSignal.timeout(10_000),
    });
  } catch {
    return new Response(null, { status: 503 });
  }
}

export async function getChatRooms(page: number): Promise<ChatRooms | null> {
  const result = await fetchChat(`?page=${page}`);
  return result.ok ? (result.json().catch(() => null) as Promise<ChatRooms | null>) : null;
}
