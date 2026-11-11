import { requireVerifiedStudent } from "@/lib/auth";
import { getSponsorStatement, SponsorApiError } from "@/lib/sponsor-api";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  await requireVerifiedStudent("/sponsor");
  const year = new URL(request.url).searchParams.get("year") ?? undefined;
  let response: Response;
  try {
    response = await getSponsorStatement(year);
  } catch (error) {
    return new Response("Your statement is unavailable. Return to your sponsor dashboard and try again.", {
      status: error instanceof SponsorApiError && [400, 401, 403].includes(error.status) ? error.status : 503,
      headers: { "Cache-Control": "private, no-store", "Content-Type": "text/plain; charset=utf-8" },
    });
  }
  return new Response(response.body, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="amaris-sponsor-statement-${/^\d{4}$/.test(year ?? "") ? year : "current"}.csv"`,
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
