import type { NextRequest } from "next/server";
import { refreshSupabaseSession } from "@/lib/supabase/proxy";

export async function proxy(request: NextRequest) {
  const response = await refreshSupabaseSession(request);
  const path = request.nextUrl.pathname;
  if (path === "/subscriptions/status" || /^\/subscriptions\/[^/]+\/checkout\/?$/.test(path) || path.startsWith("/api/subscriptions/")) {
    response.headers.set("Cache-Control", "private, no-store, max-age=0");
    response.headers.append("Vary", "Cookie");
    response.headers.set("X-Content-Type-Options", "nosniff");
    response.headers.set("X-Frame-Options", "DENY");
    response.headers.set("Content-Security-Policy", "form-action 'self' https://www.payfast.co.za https://sandbox.payfast.co.za; frame-ancestors 'none'");
  }
  return response;
}

export const config = {
  matcher: [
    "/tutor/:path*",
    "/api/tutor-applications/:path*",
    "/dashboard/:path*",
    "/documents/:path*",
    "/checkout/:path*",
    "/book-online-live-class/:path*",
    "/request-a-video/:path*",
    "/api/video-requests/:path*",
    "/subscriptions/status",
    "/subscriptions/:plan/checkout",
    "/api/subscriptions/:path*",
    "/login",
    "/register",
    "/forgot-password",
    "/reset-password/:path*",
    "/verify-email",
    "/auth/:path*",
    "/session-expired",
    "/api/auth-state",
  ],
};
