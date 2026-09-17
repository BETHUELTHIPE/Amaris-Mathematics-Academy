import tailwindcss from "@tailwindcss/vite";
import vinext from "vinext";
import { nitro } from "nitro/vite";
import { defineConfig } from "vite";

/**
 * Node/Nitro deployment configuration for hosts such as Render.
 *
 * The default vite.config.ts remains Cloudflare-native so the existing
 * Worker/D1/rate-limit bindings are preserved for the primary deployment
 * target. This alternate config deliberately avoids importing the
 * Cloudflare Vite adapter when building a standalone Node server.
 */
export default defineConfig({
  // The Node build uses Tailwind's Vite integration directly. This keeps the
  // repository's existing PostCSS pipeline untouched for the Cloudflare build.
  css: {
    postcss: { plugins: [] },
  },
  plugins: [tailwindcss(), vinext(), nitro()],
});
