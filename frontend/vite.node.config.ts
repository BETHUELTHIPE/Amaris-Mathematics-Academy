import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { nitro } from "nitro/vite";
import vinext from "vinext";
import { defineConfig } from "vite";

const root = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  define: {
    // The synthetic student exists only in non-production E2E builds.
    // Render/Nitro must still replace the compile-time symbol so the
    // production server never evaluates an undefined global.
    __E2E_SYNTHETIC_STUDENT__: JSON.stringify(false),
  },
  resolve: {
    alias: {
      "cloudflare:workers": resolve(root, "node/cloudflare-workers.ts"),
    },
  },
  plugins: [vinext(), tailwindcss(), nitro()],
});
