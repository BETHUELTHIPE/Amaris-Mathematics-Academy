import type { NextRequest } from "next/server";
import { refreshSupabaseSession } from "@/lib/supabase/proxy";

export async function proxy(request: NextRequest) {
  return refreshSupabaseSession(request);
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/documents/:path*",
    "/checkout/:path*",
    "/learn/:path*",
    "/payments/status/:path*",
    "/login",
    "/register",
    "/forgot-password",
    "/reset-password",
    "/verify-email",
    "/auth/:path*",
    "/session-expired",
    "/api/auth-state",
  ],
};
