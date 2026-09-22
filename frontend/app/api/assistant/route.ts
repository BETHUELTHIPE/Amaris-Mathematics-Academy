const cmsBaseUrl = process.env.CMS_API_URL?.replace(/\/$/, "");

function jsonResponse(body: object, status: number) {
  return Response.json(body, {
    status,
    headers: {
      "Cache-Control": "no-store",
    },
  });
}

export async function POST(request: Request) {
  let body: { question?: unknown };
  try {
    body = (await request.json()) as { question?: unknown };
  } catch {
    return jsonResponse({ detail: "Invalid JSON payload." }, 400);
  }

  const question = typeof body.question === "string" ? body.question.trim() : "";
  if (question.length < 2 || question.length > 800) {
    return jsonResponse(
      { detail: "Question must be between 2 and 800 characters." },
      400,
    );
  }

  if (!cmsBaseUrl) {
    return jsonResponse(
      {
        detail:
          "Amaris Assistant is temporarily unavailable. Please use the Contact page for assistance.",
      },
      503,
    );
  }

  try {
    const upstream = await fetch(`${cmsBaseUrl}/assistant/ask/`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question }),
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });

    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: {
        "Cache-Control": "no-store",
        "Content-Type": upstream.headers.get("content-type") || "application/json",
      },
    });
  } catch {
    return jsonResponse(
      {
        detail:
          "Amaris Assistant is temporarily unavailable. Please use the Contact page for assistance.",
      },
      503,
    );
  }
}
