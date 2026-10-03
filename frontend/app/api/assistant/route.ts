import { env } from "cloudflare:workers";
import { NextResponse, type NextRequest } from "next/server";

type AssistantResponse = {
  answer?: string;
  detail?: string;
};

function cmsBaseUrl(): string {
  const workerBindings = env as unknown as { CMS_API_URL?: string };
  return (workerBindings.CMS_API_URL || process.env.CMS_API_URL || "").replace(/\/$/, "");
}

export async function POST(request: NextRequest) {
  let message = "";
  try {
    const body = (await request.json()) as { message?: unknown };
    message = typeof body.message === "string" ? body.message.trim() : "";
  } catch {
    return NextResponse.json({ detail: "Enter a valid question." }, { status: 400 });
  }

  if (!message) {
    return NextResponse.json({ detail: "Enter a question for Amaris Assistant." }, { status: 400 });
  }
  if (message.length > 1200) {
    return NextResponse.json({ detail: "Keep your question under 1,200 characters." }, { status: 400 });
  }

  const baseUrl = cmsBaseUrl();
  if (!baseUrl) {
    return NextResponse.json({ detail: "Amaris Assistant is temporarily unavailable." }, { status: 503 });
  }

  try {
    const response = await fetch(`${baseUrl}/assistant/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ message }),
      cache: "no-store",
      signal: AbortSignal.timeout(12_000),
    });

    const payload = (await response.json().catch(() => ({}))) as AssistantResponse;
    if (!response.ok) {
      // A missing CMS route is an upstream outage; let the client show published guidance.
      const status = response.status === 429 ? 429 : response.status === 404 || response.status >= 500 ? 503 : 400;
      return NextResponse.json(
        { detail: payload.detail || "Amaris Assistant is temporarily unavailable." },
        { status, headers: { "Cache-Control": "no-store" } },
      );
    }

    if (!payload.answer?.trim()) {
      return NextResponse.json(
        { detail: "Amaris Assistant is temporarily unavailable." },
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    }

    return NextResponse.json(
      { answer: payload.answer.trim() },
      { status: 200, headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return NextResponse.json(
      { detail: "Amaris Assistant is temporarily unavailable." },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
