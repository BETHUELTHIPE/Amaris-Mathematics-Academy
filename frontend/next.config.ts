import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  compress: true,
  poweredByHeader: false,
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
