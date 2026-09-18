import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { getSupabaseConfig } from "@/lib/supabase/config";
import type { Database } from "@/lib/supabase/database.types";
import { createCorrelationReference } from "@/lib/recovery";

export async function refreshSupabaseSession(request: NextRequest) {
  const correlationReference = createCorrelationReference();
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-amaris-correlation-id", correlationReference);
  const createResponse = () => {
    const nextResponse = NextResponse.next({ request: { headers: requestHeaders } });
    nextResponse.headers.set("x-correlation-id", correlationReference);
    return nextResponse;
  };
  const config = getSupabaseConfig();
  if (!config) return createResponse();

  let response = createResponse();
  const supabase = createServerClient<Database>(config.url, config.publishableKey, {
    auth: {
      flowType: "pkce",
      autoRefreshToken: false,
      detectSessionInUrl: false,
      persistSession: true,
    },
    cookieOptions: {
      path: "/",
      sameSite: "lax",
      secure: request.nextUrl.protocol === "https:",
      httpOnly: true,
    },
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet, headersToSet) {
        cookiesToSet.forEach(({ name, value }) =>
          request.cookies.set(name, value),
        );
        response = createResponse();
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options),
        );
        Object.entries(headersToSet).forEach(([key, value]) =>
          response.headers.set(key, value),
        );
      },
    },
  });

  // Verify the token and refresh it before any page or action reads identity.
  const { error: claimsError } = await supabase.auth.getClaims();
  const hasAuthCookie = request.cookies.getAll().some(({ name }) => /^sb-.+-auth-token(?:\.\d+)?$/.test(name));
  const protectedPath = ["/dashboard", "/documents", "/checkout", "/learn", "/payments/status"].some((path) => request.nextUrl.pathname.startsWith(path));
  if (claimsError && hasAuthCookie && protectedPath) {
    const returnTo = `${request.nextUrl.pathname}${request.nextUrl.search}`;
    const destination = new URL("/session-expired", request.url);
    destination.searchParams.set("next", returnTo);
    const redirectResponse = NextResponse.redirect(destination);
    redirectResponse.headers.set("x-correlation-id", correlationReference);
    return redirectResponse;
  }
  return response;
}
