import { tutorFetch, TutorApiError } from "@/lib/tutor-api";
import { personnelRequestError, readPersonnelJSON } from "@/lib/tutor-personnel-request.mjs";

export const dynamic = "force-dynamic";
function response(body: unknown, status = 200) {
  return Response.json(body, { status, headers: { "Cache-Control": "private, no-store", Vary: "Cookie" } });
}

export async function GET(request: Request) {
  const page = new URL(request.url).searchParams.get("page") || "1";
  if (!/^\d{1,6}$/.test(page)) return response({ detail: "Invalid page number." }, 400);
  try { return response(await tutorFetch(`/tutor/forms/?page=${page}`)); }
  catch (error) {
    return response({ detail: "Unable to load your saved forms. Please retry." }, error instanceof TutorApiError ? error.status : 503);
  }
}

export async function POST(request: Request) {
  const invalid = personnelRequestError(request);
  if (invalid) return response({ detail: invalid.detail }, invalid.status);
  let values: Record<string, unknown>;
  try { values = await readPersonnelJSON(request); }
  catch { return response({ detail: "Invalid or oversized form. Check the details." }, 400); }
  try { return response(await tutorFetch("/tutor/forms/", "POST", values), 201); }
  catch (error) {
    if (error instanceof TutorApiError) return response({ detail: error.message }, error.status);
    return response({ detail: "Submission interrupted. Retry the same form and details." }, 503);
  }
}
