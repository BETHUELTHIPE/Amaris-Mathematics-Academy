import { tutorFetch, TutorApiError } from "@/lib/tutor-api";
import { personnelRequestError, readPersonnelJSON } from "@/lib/tutor-personnel-request.mjs";

export const dynamic = "force-dynamic";
function response(body: unknown, status = 200) {
  return Response.json(body, { status, headers: { "Cache-Control": "private, no-store", Vary: "Cookie" } });
}

export async function GET() {
  try { return response(await tutorFetch("/tutor/contracts/")); }
  catch (error) {
    return response({ detail: "Unable to load your employment contract. Please retry." }, error instanceof TutorApiError ? error.status : 503);
  }
}

export async function POST(request: Request) {
  const invalid = personnelRequestError(request);
  if (invalid) return response({ detail: invalid.detail }, invalid.status);
  let values: Record<string, unknown>;
  try { values = await readPersonnelJSON(request); }
  catch { return response({ detail: "Invalid or oversized contract. Check the details." }, 400); }
  try { return response(await tutorFetch("/tutor/contracts/", "POST", values), 201); }
  catch (error) {
    if (error instanceof TutorApiError) return response({ detail: error.message }, error.status);
    return response({ detail: "Submission interrupted. Retry the same contract and details." }, 503);
  }
}
