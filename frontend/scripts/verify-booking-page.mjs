import { pathToFileURL } from "node:url";

const protectedStatuses = new Set([301, 302, 303, 307, 308]);

function redirectsToVerifiedLogin(response, requestedUrl) {
  if (!protectedStatuses.has(response.status)) return false;
  const destination = response.headers.get("location");
  if (!destination) return false;

  let login;
  try {
    login = new URL(destination, requestedUrl);
  } catch {
    return false;
  }

  const source = new URL(requestedUrl);
  const returnTo = login.searchParams.get("next");
  if (login.origin !== source.origin || login.pathname !== "/login" || !returnTo) return false;
  if (!returnTo.startsWith("/book-online-live-class")) return false;
  // Reject a nested malicious redirect or a different target.
  try {
    const saved = new URL(returnTo, source.origin);
    return saved.origin === source.origin && saved.pathname === "/book-online-live-class";
  } catch {
    return false;
  }
}

export async function verifyBookingPage(url, {
  fetchPage = fetch,
  wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  log = console.log,
} = {}) {
  // This probe is anonymous by design. A public booking page is now a security
  // regression, even when it renders perfectly and responds with HTTP 200.
  for (let attempt = 1; attempt <= 4; attempt += 1) {
    let response;
    try {
      response = await fetchPage(url, {
        redirect: "manual",
        signal: AbortSignal.timeout(30_000),
      });
    } catch (error) {
      if (!["TimeoutError", "AbortError", "TypeError"].includes(error.name)) throw error;
      log(`Protected booking attempt ${attempt}: ${error.name}`);
      if (attempt === 4) throw new Error("Booking authentication gate did not respond within the cold-start window");
      await wait(5_000);
      continue;
    }

    if ([502, 503, 504].includes(response.status)) {
      log(`Booking authentication attempt ${attempt}: HTTP ${response.status}`);
      if (attempt === 4) throw new Error(`Booking authentication gate remained unavailable: HTTP ${response.status}`);
      await wait(5_000);
      continue;
    }

    if (!redirectsToVerifiedLogin(response, url)) {
      throw new Error(`Booking authentication gate bypassed or returned an unsafe login redirect: HTTP ${response.status}`);
    }
    log(`Protected booking page passed on attempt ${attempt}: anonymous visitor redirected to login with a safe booking return path`);
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
