import { NextResponse, type NextRequest } from "next/server";

import { normalizeCmsApiBaseUrl } from "@/lib/cms-api-url";

type AssistantResponse = {
  answer?: string;
  detail?: string;
};

function cmsBaseUrl(request: NextRequest): string {
  const configured = (process.env.CMS_API_URL || "").trim();
  if (configured) {
    try {
      return normalizeCmsApiBaseUrl(configured);
    } catch {
      return "";
    }
  }

  // Never send unconfigured staging traffic to production.
  if (request.nextUrl.hostname === "amaris-mathematics-academy-live-students.onrender.com") {
    return "https://amaris-production-web.onrender.com/api/v1";
  }
  return "";
}

/** Only answers already established by published site routes and booking rules. */
function publishedAnswer(message: string): string | null {
  const question = message.toLocaleLowerCase("en");
  const registration = /\b(register|registration|sign\s*up|signup)\b/.test(question);
  const lessons = /\b(lesson|lessons|classes|class|session|sessions|duration)\b/.test(question)
    || question.includes("how long");
  if (!registration && !lessons) return null;

  const answer: string[] = [];
  if (registration) {
    answer.push(
      "To register, visit /register and choose Google registration or the email registration form. " +
      "After email registration, verify your email using the code or secure link at /verify-email, then sign in at /login.",
    );
  }
  if (lessons) {
    answer.push(
      "Live Zoom classes last one hour (60 minutes). " +
      "Choose an available tutor and time at /book-online-live-class. " +
      "Recorded course lesson counts and total guided hours vary; see /courses for details.",
    );
  }
  return answer.join("\n\n");
}

function publishedResponse(answer: string) {
  return NextResponse.json({ answer }, { status: 200, headers: { "Cache-Control": "no-store" } });
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

  const baseUrl = cmsBaseUrl(request);
  const fallback = publishedAnswer(message);
  if (!baseUrl) {
    return fallback ? publishedResponse(fallback) : NextResponse.json(
      { detail: "Amaris Assistant is temporarily unavailable." },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }

  try {
    const response = await fetch(baseUrl + "/assistant/", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ message }),
      cache: "no-store",
      signal: AbortSignal.timeout(20_000),
    });

    const payload = (await response.json().catch(() => ({}))) as AssistantResponse;
    if (!response.ok) {
      // Preserve rate limits and validation errors; never bypass 429 throttling.
      if (response.status >= 500 && fallback) return publishedResponse(fallback);
      const status = response.status === 429 ? 429 : response.status >= 500 ? 503 : 400;
      return NextResponse.json(
        { detail: payload.detail || "Amaris Assistant is temporarily unavailable." },
        { status, headers: { "Cache-Control": "no-store" } },
      );
    }

    if (!payload.answer?.trim()) {
      if (fallback) return publishedResponse(fallback);
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
    if (fallback) return publishedResponse(fallback);
    return NextResponse.json(
      { detail: "Amaris Assistant is temporarily unavailable." },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
