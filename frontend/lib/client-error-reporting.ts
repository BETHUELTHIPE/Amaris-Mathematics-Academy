export function reportClientError(reference: string | undefined): void {
  const payload = JSON.stringify({
    reference: reference ?? "unavailable",
    path: window.location.pathname,
  });

  try {
    if (navigator.sendBeacon) {
      navigator.sendBeacon("/api/client-errors", new Blob([payload], { type: "application/json" }));
      return;
    }
    void fetch("/api/client-errors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
      keepalive: true,
      credentials: "same-origin",
    });
  } catch {
    // Reporting is best-effort and must never interfere with recovery UI.
  }
}
