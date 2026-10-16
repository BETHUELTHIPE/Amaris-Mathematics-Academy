import { defineConfig } from "nitro";

// Pre-compress only public static build assets; sensitive student and
// payment responses are never cached by this setting.
export default defineConfig({
  compressPublicAssets: { gzip: true, brotli: true, zstd: false },
});
