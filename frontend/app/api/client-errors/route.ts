import { NextResponse, type NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as Record<string, unknown>;
    const reference = typeof body.reference === "string" ? body.reference.slice(0, 80) : "unavailable";
    const path = typeof body.path === "string" && body.path.startsWith("/") ? body.path.slice(0, 200) : "/";
    const release = process.env.RELEASE_SHA ?? process.env.GITHUB_SHA ?? "unknown";
    console.error("Client render error", { reference, path, release });
  } catch {
    // Error reporting is never allowed to fail the student-facing response.
  }
  return new NextResponse(null, { status: 204, headers: { "Cache-Control": "no-store" } });
}
