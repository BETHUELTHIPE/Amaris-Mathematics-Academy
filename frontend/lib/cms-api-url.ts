/**
 * Django routes are mounted under /api/v1/ even when the Render origin is
 * supplied without that prefix. Keep all server-to-server callers consistent.
 */
export function normalizeCmsApiBaseUrl(value: string): string {
  const base = new URL(value.trim());
  if (!["https:", "http:"].includes(base.protocol) || !base.hostname) {
    throw new Error("CMS_API_URL must be an HTTP(S) URL.");
  }
  if (base.username || base.password || base.search || base.hash) {
    throw new Error("CMS_API_URL must not contain credentials, a query or a fragment.");
  }
  const path = base.pathname.replace(/\/+$/, "");
  if (path && path !== "/api/v1") {
    throw new Error("CMS_API_URL must point to the Django origin or /api/v1.");
  }
  base.pathname = "/api/v1";
  return base.toString().replace(/\/$/, "");
}
