import { NextResponse, type NextRequest } from "next/server";
import { validVital } from "@/lib/web-vitals";

export const dynamic = "force-dynamic";

function upstream(): string | null {
  const raw = process.env.CMS_API_URL;
  if (!raw) return null;
  try {
    const base = new URL(raw);
    if (
      base.protocol !== "https:" ||
      !["amaris-production-web.onrender.com", "amaris-mathematics-academy-staging.onrender.com"].includes(base.hostname) ||
      base.username || base.password
    ) return null;
    return new URL("/api/v1/web-vitals/ingest/", base.origin).href;
  } catch {
    return null;
  }
}

export async function POST(request: NextRequest) {
  // No credentials, cookies, IPs, paths or queries are forwarded or recorded.
  if (request.headers.get("sec-fetch-site") === "cross-site") {
    return new NextResponse(null, { status: 403, headers: { "Cache-Control": "no-store" } });
  }
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return new NextResponse(null, { status: 415, headers: { "Cache-Control": "no-store" } });
  }
  const token = process.env.WEB_VITALS_INGEST_TOKEN ?? "";
  const url = upstream();
  if (token.length < 32 || !url) {
    return new NextResponse(null, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
  let body: string;
  try {
    const len = Number(request.headers.get("content-length") ?? "0");
    if (!Number.isFinite(len) || len > 768) return new NextResponse(null, { status: 413 });
    body = await request.text();
    if (body.length > 768 || !validVital(JSON.parse(body))) {
      return new NextResponse(null, { status: 400 });
    }
  } catch {
    return new NextResponse(null, { status: 400 });
  }

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Amaris-RUM-Token": token,
      },
      body,
      redirect: "error",
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    return new NextResponse(null, {
      status: response.status === 204 ? 204 : response.status === 429 ? 429 : 503,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return new NextResponse(null, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
