import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { getSupabaseConfig } from "@/lib/supabase/config";
import type { Database } from "@/lib/supabase/database.types";
import { createCorrelationReference } from "@/lib/recovery";

declare const __E2E_SYNTHETIC_STUDENT__: boolean;

export async function refreshSupabaseSession(request: NextRequest) {
  const correlationReference = createCorrelationReference();
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-amaris-correlation-id", correlationReference);
  const createResponse = () => {
    const nextResponse = NextResponse.next({ request: { headers: requestHeaders } });
    nextResponse.headers.set("x-correlation-id", correlationReference);
    return nextResponse;
  };

  const protectedPath = ["/dashboard", "/documents", "/checkout", "/learn"].some(
    (path) => request.nextUrl.pathname.startsWith(path),
  );
  const returnTo = `${request.nextUrl.pathname}${request.nextUrl.search}`;
  const hasAuthCookie = request.cookies
    .getAll()
    .some(({ name }) => /^sb-.+-auth-token(?:\.\d+)?$/.test(name));

  // Development E2E uses a compile-time synthetic identity so protected
  // responsive-browser checks exercise the real protected pages. The
  // production Nitro build hard-codes this symbol to false.
  if (protectedPath && __E2E_SYNTHETIC_STUDENT__) {
    return createResponse();
  }

  // Enforce authentication at the request boundary. This produces a real
  // HTTP redirect on Node/Vinext instead of relying on a server-component
  // redirect that may be serialized into a 200 HTML shell.
  if (protectedPath && !hasAuthCookie) {
    const destination = new URL("/login", request.url);
    destination.searchParams.set("next", returnTo);
    const redirectResponse = NextResponse.redirect(destination);
    redirectResponse.headers.set("x-correlation-id", correlationReference);
    return redirectResponse;
  }

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

  // Verify and refresh an existing token before protected pages/actions read it.
  const { error: claimsError } = await supabase.auth.getClaims();
  if (claimsError && protectedPath) {
    const destination = new URL("/session-expired", request.url);
    destination.searchParams.set("next", returnTo);
    const redirectResponse = NextResponse.redirect(destination);
    redirectResponse.headers.set("x-correlation-id", correlationReference);
    return redirectResponse;
  }
  return response;
}
