import { NextRequest, NextResponse } from "next/server";
import { BOOKING_ROOM_ID, MESSAGE_MAX_LENGTH } from "@/lib/chat";
import { fetchChat } from "@/lib/chat-api";

export const dynamic = "force-dynamic";

const privateHeaders = { "Cache-Control": "private, no-store, max-age=0", Vary: "Cookie" };
type Context = { params: Promise<{ room: string }> };

function errorResponse(status: number, detail: string) {
  return NextResponse.json({ detail }, { status, headers: privateHeaders });
}

async function forward(context: Context, query = "", init?: RequestInit): Promise<Response> {
  const { room } = await context.params;
  if (room !== "support" && !BOOKING_ROOM_ID.test(room)) {
    return errorResponse(404, "This conversation is unavailable.");
  }

  const result = await fetchChat(`${room}/messages/${query}`, init);
  if (result.ok) {
    return new Response(result.body, {
      status: result.status,
      headers: { ...privateHeaders, "Content-Type": "application/json" },
    });
  }
  switch (result.status) {
    case 400: return errorResponse(400, "Check your message and try again.");
    case 401:
    case 403: return errorResponse(result.status, "Sign in with a verified account to use Messages.");
    case 404: return errorResponse(404, "This conversation is unavailable.");
    case 409: return errorResponse(409, "This message was already submitted. Refresh the conversation.");
    case 429: return errorResponse(429, "Too many requests. Wait a moment and try again.");
    default: return errorResponse(503, "Messages are temporarily unavailable. Please try again.");
  }
}

function messageQuery(request: NextRequest) {
  const query = new URLSearchParams();
  const assignment = request.nextUrl.searchParams.get("assignment");
  if (assignment && /^[a-f0-9]{64}$/.test(assignment)) query.set("assignment", assignment);
  return query;
}

export async function GET(request: NextRequest, context: Context) {
  const query = messageQuery(request);
  for (const key of ["before", "after"]) {
    const value = request.nextUrl.searchParams.get(key);
    if (value !== null) query.set(key, value);
  }
  return forward(context, `?${query}`);
}

export async function POST(request: NextRequest, context: Context) {
  const expectedOrigin = new URL(request.nextUrl.toString());
  const protocol = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim();
  if (protocol === "https" || protocol === "http") expectedOrigin.protocol = `${protocol}:`;
  if (request.headers.get("origin") !== expectedOrigin.origin) {
    return errorResponse(403, "Cross-site requests are unavailable.");
  }
  if (request.headers.get("content-type")?.split(";")[0]?.trim() !== "application/json") {
    return errorResponse(415, "Send a text message.");
  }
  if (Number(request.headers.get("content-length")) > 16_384) {
    return errorResponse(413, "This message is too long.");
  }
  const data = await request.json().catch(() => null) as { text?: unknown; client_id?: unknown } | null;
  if (
    typeof data?.text !== "string" || !data.text.trim() || data.text.length > MESSAGE_MAX_LENGTH ||
    typeof data.client_id !== "string" || !BOOKING_ROOM_ID.test(data.client_id)
  ) {
    return errorResponse(400, "Enter a message of 1–2,000 characters.");
  }
  return forward(context, `?${messageQuery(request)}`, {
    method: "POST",
    body: JSON.stringify({ text: data.text, client_id: data.client_id }),
  });
}
