import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { requireSupabaseConfig } from "@/lib/supabase/config";
import type { Database } from "@/lib/supabase/database.types";

export async function createSupabaseServerClient() {
  const cookieStore = await cookies();
  const { url, publishableKey } = requireSupabaseConfig();

  return createServerClient<Database>(url, publishableKey, {
    auth: {
      flowType: "pkce",
      autoRefreshToken: false,
      detectSessionInUrl: false,
      persistSession: true,
    },
    cookieOptions: {
      path: "/",
      sameSite: "lax",
      secure: getSecureCookieSetting(),
      httpOnly: true,
    },
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => {
            cookieStore.set(name, value, options);
          });
        } catch {
          // Server Components cannot write cookies. The root proxy refreshes
          // and persists sessions before protected pages render.
        }
      },
    },
  });
}

function getSecureCookieSetting(): boolean {
  return process.env.NODE_ENV === "production";
}
