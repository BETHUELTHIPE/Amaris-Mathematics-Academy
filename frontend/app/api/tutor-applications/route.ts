import { parseLocation } from "@/lib/location-server";
import { countryName } from "@/lib/location-data";
import { NextResponse } from "next/server";
import { applicantToken, applicationRequest, ApplicationError } from "@/lib/tutor-applications";
import { validateTutorAvailability } from "@/lib/tutor-availability";

export const dynamic = "force-dynamic";
const privateHeaders = { "Cache-Control": "private, no-store" };
const MAX_BODY = 16 * 1024 * 1024;

export async function POST(request: Request): Promise<Response> {
  const wantsJson = request.headers.get("accept")?.includes("application/json");
  function result(body: unknown, status: number) {
    if (wantsJson) return NextResponse.json(body, { status, headers: privateHeaders });
    const url = new URL("/tutor/apply", request.url);
    if (status >= 400) url.searchParams.set("error", "Application not submitted. Check all fields and files, then try again. If you already submitted, sign in to view its status.");
    return NextResponse.redirect(url, { status: 303, headers: privateHeaders });
  }
  // Cookie-based BFF requests must originate from this site; Django receives only a validated bearer token.
  if (request.headers.get("origin") !== new URL(request.url).origin) {
    return result({ detail: "Please submit this form from the Amaris website." }, 403);
  }
  try {
    const token = await applicantToken();
    if (!request.headers.get("content-type")?.startsWith("multipart/form-data;")) {
      return result({ detail: "Attach your documents using the application form." }, 400);
    }
    if (Number(request.headers.get("content-length")) > MAX_BODY) {
      return result({ documents: ["Files must total no more than 15 MB."] }, 413);
    }
    const reader = request.body?.getReader();
    if (!reader) return result({ detail: "The form is empty." }, 400);
    const chunks: Uint8Array<ArrayBuffer>[] = [];
    let length = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > MAX_BODY) {
        await reader.cancel();
        return result({ documents: ["Files must total no more than 15 MB."] }, 413);
      }
      chunks.push(new Uint8Array(value));
    }
    const data = await new Response(new Blob(chunks), {
      headers: { "Content-Type": request.headers.get("content-type")! },
    }).formData();
    if (data.get("_action") !== "retry-email") {
      const location = await parseLocation(Object.fromEntries(data));
      if (!location.value) return result(Object.fromEntries(Object.entries(location.errors).map(([field, message]) => [field, [message]])), 400);
      // Keep the summary readable for older API releases during an ordered rollout.
      data.set("location", [location.value.city, location.value.province, countryName(location.value.country)].join(", ").slice(0, 120));
      // Derive the stored schedule from validated date/time controls, never from client text.
      const availability = validateTutorAvailability(data);
      if (!availability.ok) return result({ availability: [availability.error] }, 400);
      data.set("availability", availability.summary);
      data.delete("availability_start");
      data.delete("availability_duration_hours");
    }
    const response = await applicationRequest(data.get("_action") === "retry-email" ? "acknowledgement/" : "", { method: "POST", body: data }, token);
    const body = await response.json().catch(() => ({ detail: "Applications are temporarily unavailable. Please retry." }));
    return result(body, response.status);
  } catch (error) {
    return result({ detail: error instanceof ApplicationError ? error.message : "The form could not be read. Please check your files and retry." }, error instanceof ApplicationError ? error.status : 400);
  }
}
