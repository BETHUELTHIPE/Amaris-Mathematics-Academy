import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { nitro } from "nitro/vite";
import vinext from "vinext";
import { defineConfig } from "vite";

const root = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "cloudflare:workers": resolve(root, "node/cloudflare-workers.ts"),
    },
  },
  plugins: [vinext(), tailwindcss(), nitro()],
});
