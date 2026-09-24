/**
 * Node-host compatibility shim for code that normally reads Cloudflare Worker env.
 *
 * Core student/auth/payment state remains in Supabase + Django. D1 is not
 * emulated here; legacy D1 mirror writes are already non-critical/fallback-only.
 */
export const env = new Proxy<Record<string, string | undefined>>(
  {},
  {
    get(_target, property) {
      return process.env[String(property)];
    },
    has(_target, property) {
      return process.env[String(property)] !== undefined;
    },
  },
);
