export function personnelRequestError(request) {
  const origin = request.headers.get("origin");
  if (!origin || origin !== new URL(request.url).origin || request.headers.get("sec-fetch-site") === "cross-site") {
    return { status: 403, detail: "Submit this form from your tutor dashboard." };
  }
  if (request.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "application/json") {
    return { status: 415, detail: "Submit the form as JSON." };
  }
  const length = request.headers.get("content-length");
  if (length && (!/^\d+$/.test(length) || Number(length) > 65536)) {
    return { status: 413, detail: "The form is too large." };
  }
  return null;
}

export async function readPersonnelJSON(request) {
  if (!request.body) throw new Error("Empty form");
  const reader = request.body.getReader();
  const chunks = [];
  let length = 0;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      length += value.length;
      if (length > 65536) throw new Error("Form too large");
      chunks.push(value);
    }
  } finally { await reader.cancel(); }
  const data = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { data.set(chunk, offset); offset += chunk.length; }
  const result = JSON.parse(new TextDecoder().decode(data));
  if (!result || Array.isArray(result) || typeof result !== "object") throw new Error("Invalid form");
  return result;
}
