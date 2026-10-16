// Render installs Nitro during its Node build; it is not a direct package
// dependency of the regular Cloudflare/frontend typecheck environment.
// A plain config object avoids requiring Nitro types in standard CI.
export default {
  // Compress static public JS/CSS/SVG only, never student/payment responses.
  compressPublicAssets: { gzip: true, brotli: true, zstd: false },
};
