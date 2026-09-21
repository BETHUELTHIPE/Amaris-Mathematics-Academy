/** Cloudflare Worker entry point for the vinext-starter template. */
import { handleImageOptimization, DEFAULT_DEVICE_SIZES, DEFAULT_IMAGE_SIZES } from "vinext/server/image-optimization";
import handler from "vinext/server/app-router-entry";

interface Env {
  ASSETS: Fetcher;
  DB: D1Database;
  AUTH_RATE_LIMITER?: RateLimit;
  REGISTER_RATE_LIMITER?: RateLimit;
  CHECKOUT_RATE_LIMITER?: RateLimit;
  PASSWORD_RESET_RATE_LIMITER?: RateLimit;
  CSP_REPORT_ONLY?: string;
  IMAGES: {
    input(stream: ReadableStream): {
      transform(options: Record<string, unknown>): {
        output(options: { format: string; quality: number }): Promise<{ response(): Response }>;
      };
    };
  };
}

interface ExecutionContext {
  waitUntil(promise: Promise<unknown>): void;
  passThroughOnException(): void;
}

const protectedPrefixes = ["/dashboard", "/documents", "/checkout", "/learn", "/api/auth-state", "/login", "/register", "/forgot-password", "/reset-password", "/verify-email", "/auth", "/session-expired"];
const mutatingMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const csp = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  "style-src 'self' 'unsafe-inline'",
  "script-src 'self' 'unsafe-inline'",
  "connect-src 'self' https://*.supabase.co",
  "media-src 'self' https:",
  "upgrade-insecure-requests",
  "report-uri /api/csp-report",
].join("; ");

async function rateLimitResponse(request: Request, env: Env, pathname: string): Promise<Response | null> {
  if (!mutatingMethods.has(request.method.toUpperCase())) return null;

  let limiter: RateLimit | undefined;
  let scope = "";
  if (pathname === "/login" || pathname === "/verify-email" || pathname.startsWith("/auth/")) {
    limiter = env.AUTH_RATE_LIMITER;
    scope = "auth";
  } else if (pathname === "/register") {
    limiter = env.REGISTER_RATE_LIMITER;
    scope = "register";
  } else if (pathname === "/forgot-password" || pathname === "/reset-password") {
    limiter = env.PASSWORD_RESET_RATE_LIMITER;
    scope = "password-reset";
  } else if (pathname === "/checkout" || pathname.startsWith("/checkout/")) {
    limiter = env.CHECKOUT_RATE_LIMITER;
    scope = "checkout";
  }

  if (!limiter) return null;
  const actor = request.headers.get("cf-connecting-ip") || request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";
  const { success } = await limiter.limit({ key: `${scope}:${actor}` });
  if (success) return null;

  const response = new Response("Too many requests. Please try again shortly.", {
    status: 429,
    headers: { "Retry-After": "60", "Cache-Control": "no-store" },
  });
  return secureResponse(response, pathname, env);
}

function secureResponse(response: Response, pathname: string, env: Env, personalized = false): Response {
  const secured = new Response(response.body, response);
  secured.headers.set("X-Content-Type-Options", "nosniff");
  secured.headers.set("X-Frame-Options", "DENY");
  secured.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  secured.headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(self)");
  secured.headers.set("Cross-Origin-Opener-Policy", "same-origin");
  secured.headers.set("Cross-Origin-Resource-Policy", "same-site");

  if (env.CSP_REPORT_ONLY?.toLowerCase() === "true") {
    secured.headers.set("Content-Security-Policy-Report-Only", csp);
  } else {
    secured.headers.set("Content-Security-Policy", csp);
  }

  if (pathname === "/") {
    secured.headers.append(
      "Link",
      '</amaris-math-hero.webp>; rel=preload; as=image; type="image/webp"; fetchpriority=high',
    );
  }

  if (personalized || secured.headers.has("Set-Cookie") || protectedPrefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))) {
    secured.headers.set("Cache-Control", "private, no-store, max-age=0");
    secured.headers.append("Vary", "Cookie");
  }
  return secured;
}

const worker = {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const limited = await rateLimitResponse(request, env, url.pathname);
    if (limited) return limited;

    if (url.pathname === "/_vinext/image") {
      const allowedWidths = [...DEFAULT_DEVICE_SIZES, ...DEFAULT_IMAGE_SIZES];
      const imageResponse = await handleImageOptimization(
        request,
        {
          fetchAsset: (path) => env.ASSETS.fetch(new Request(new URL(path, request.url))),
          transformImage: async (body, { width, format, quality }) => {
            const result = await env.IMAGES.input(body).transform(width > 0 ? { width } : {}).output({ format, quality });
            return result.response();
          },
        },
        allowedWidths,
      );
      return secureResponse(imageResponse, url.pathname, env);
    }

    const response = await handler.fetch(request, env, ctx);
    return secureResponse(response, url.pathname, env, /(?:^|;\s*)sb-.+-auth-token(?:\.\d+)?=/.test(request.headers.get("cookie") ?? ""));
  },
};

export default worker;
