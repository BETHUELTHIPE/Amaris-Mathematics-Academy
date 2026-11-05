import { NextResponse, type NextRequest } from "next/server";

function hostOnly(value: unknown): string {
  if (typeof value !== "string" || !value) return "";
  try {
    return new URL(value).hostname;
  } catch {
    return "invalid";
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as Record<string, unknown>;
    const report = (body["csp-report"] ?? body) as Record<string, unknown>;
    console.warn("CSP violation", {
      violatedDirective: String(report["violated-directive"] ?? report["effective-directive"] ?? "unknown").slice(0, 120),
      blockedHost: hostOnly(report["blocked-uri"]),
      documentHost: hostOnly(report["document-uri"]),
    });
  } catch {
    // CSP reporting must never become an availability dependency.
  }
  return new NextResponse(null, {
    status: 204,
    headers: { "Cache-Control": "no-store" },
  });
}
