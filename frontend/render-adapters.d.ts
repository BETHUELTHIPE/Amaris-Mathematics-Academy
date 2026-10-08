// Render installs these build adapters separately from the shared frontend lockfile.
// Keep type checking valid both before and after those adapters are installed.
declare module "@tailwindcss/vite" {
  import type { PluginOption } from "vite";
  export default function tailwindcss(): PluginOption;
}

declare module "nitro/vite" {
  import type { PluginOption } from "vite";
  export function nitro(): PluginOption;
}
