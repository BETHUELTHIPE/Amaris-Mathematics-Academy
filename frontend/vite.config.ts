import vinext from "vinext";
import { defineConfig } from "vite";
import hostingConfig from "./.openai/hosting.json";
import { sites } from "./build/sites-vite-plugin";

const { r2 } = hostingConfig;

// macOS Seatbelt blocks FSEvents, so Codex previews need polling for HMR.
const isCodexSeatbeltSandbox = process.env.CODEX_SANDBOX === "seatbelt";
const syntheticE2EStudent =
  process.env.NODE_ENV !== "production" && process.env.E2E_SYNTHETIC_STUDENT === "true";

const localBindingConfig = {
  main: "./worker/index.ts",
  compatibility_flags: ["nodejs_compat"],
  vars: {
    CSP_REPORT_ONLY: process.env.CSP_REPORT_ONLY ?? "false",
    CMS_API_URL: process.env.CMS_API_URL ?? "",
  },
  ratelimits: [
    { name: "AUTH_RATE_LIMITER", namespace_id: "41001", simple: { limit: 10, period: 60 as const } },
    { name: "REGISTER_RATE_LIMITER", namespace_id: "41002", simple: { limit: 5, period: 60 as const } },
    { name: "PASSWORD_RESET_RATE_LIMITER", namespace_id: "41003", simple: { limit: 5, period: 60 as const } },
    { name: "CHECKOUT_RATE_LIMITER", namespace_id: "41004", simple: { limit: 30, period: 60 as const } },
  ],
  // Supabase is the only authoritative application database; no D1 binding.
  d1_databases: [],
  r2_buckets: r2
    ? [
        {
          binding: r2,
          bucket_name: "site-creator-r2",
        },
      ]
    : [],
};

export default defineConfig(async () => {
  // Keep Wrangler and Miniflare state project-local. These are non-secret tool
  // settings; application environment belongs in ignored `.env*` files.
  process.env.WRANGLER_WRITE_LOGS ??= "false";
  process.env.WRANGLER_LOG_PATH ??= ".wrangler/logs";
  process.env.MINIFLARE_REGISTRY_PATH ??= ".wrangler/registry";

  // Wrangler snapshots its log path while the Cloudflare plugin is imported.
  const { cloudflare } = await import("@cloudflare/vite-plugin");

  return {
    define: {
      // Cloudflare worker modules do not inherit arbitrary Node process.env values.
      // Compile this non-secret test switch into development E2E builds only.
      __E2E_SYNTHETIC_STUDENT__: JSON.stringify(syntheticE2EStudent),
    },
    server: {
      host: "0.0.0.0",
      allowedHosts: ["terminal.local"],
      ...(isCodexSeatbeltSandbox
        ? { watch: { useFsEvents: false, usePolling: true } }
        : {}),
    },
    plugins: [
      vinext(),
      sites(),
      cloudflare({
        viteEnvironment: { name: "rsc", childEnvironments: ["ssr"] },
        inspectorPort: false,
        config: localBindingConfig,
      }),
    ],
  };
});
