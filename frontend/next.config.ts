import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  compress: true,
  poweredByHeader: false,
  async headers() {
    return [{ source: "/sponsor/:path*", headers: [
      { key: "Cache-Control", value: "private, no-store, max-age=0" },
      { key: "Vary", value: "Cookie" },
    ] }];
  },
  images: {
    formats: ["image/avif", "image/webp"],
    minimumCacheTTL: 86400,
    // The Cloudflare/Vinext development worker does not expose production
    // ASSETS/IMAGES bindings. Serve source images directly in development so
    // browser/accessibility tests are not masked by the dev-only optimizer.
    unoptimized: process.env.NODE_ENV !== "production",
  },
};

export default nextConfig;
