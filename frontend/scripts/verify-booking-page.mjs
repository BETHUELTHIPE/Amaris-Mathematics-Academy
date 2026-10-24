import { pathToFileURL } from "node:url";

export async function verifyBookingPage(url, {
  fetchPage = fetch,
  wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  log = console.log,
} = {}) {
  for (let attempt = 1; attempt <= 4; attempt += 1) {
    let response;
    let body;
    try {
      response = await fetchPage(url, {
        redirect: "follow",
        signal: AbortSignal.timeout(30_000),
      });
      body = await response.text();
    } catch (error) {
      if (!["TimeoutError", "AbortError", "TypeError"].includes(error.name)) throw error;
      log(`Booking frontend attempt ${attempt}: ${error.name}`);
      if (attempt === 4) throw new Error("Booking frontend did not respond within the cold-start window");
      await wait(5_000);
      continue;
    }

    if ([502, 503, 504].includes(response.status)) {
      log(`Booking frontend attempt ${attempt}: HTTP ${response.status}`);
      if (attempt === 4) throw new Error(`Booking frontend remained unavailable: HTTP ${response.status}`);
      await wait(5_000);
      continue;
    }
    if (response.status !== 200) throw new Error(`Booking page returned HTTP ${response.status}`);
    // React includes unused not-found boundaries in its serialized RSC data.
    // Check server-rendered text, not scripts that describe fallback components.
    const renderedText = body
      .replace(/<!--[^]*?-->/g, " ")
      .replace(/<(script|style)\b[^>]*>[^]*?<\/\1\s*>/gi, " ")
      .replace(/<[^>]*>/g, " ")
      .replace(/\s+/g, " ");
    if (/We could not find that page/i.test(renderedText)) throw new Error("Booking page rendered the branded 404 response");
    for (const content of [/Choose your programme/i, /Available Zoom slots/i, /R250/i]) {
      if (!content.test(renderedText)) throw new Error(`Booking page is missing required content: ${content.source}`);
    }
    log(`Booking page passed on attempt ${attempt}: HTTP 200 with programme, slots and R250 content`);
    return;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const url = new URL("/book-online-live-class", process.argv[2]);
  if (url.protocol !== "https:") throw new Error("Staging frontend must use HTTPS");
  verifyBookingPage(url).catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
