import http from "node:http";
import { spawn } from "node:child_process";
import { brotliCompress, gzip } from "node:zlib";
import { promisify } from "node:util";

const brotliCompressAsync = promisify(brotliCompress);
const gzipAsync = promisify(gzip);

const upstreamHost = "127.0.0.1";
const upstreamPort = 3002;
const proxyHost = "127.0.0.1";
const proxyPort = 3001;
const readyUrl = `http://${upstreamHost}:${upstreamPort}/`;

const compressibleContentType = /^(?:text\/|application\/(?:javascript|json|x-javascript|xml))/i;

const preview = spawn(
  process.platform === "win32" ? "npm.cmd" : "npm",
  ["exec", "--", "vite", "preview", "--host", upstreamHost, "--port", String(upstreamPort)],
  {
    env: {
      ...process.env,
      WRANGLER_LOG_PATH: process.env.WRANGLER_LOG_PATH || ".wrangler/wrangler.log",
    },
    stdio: ["ignore", "inherit", "inherit"],
  },
);

preview.on("exit", (code, signal) => {
  if (!shuttingDown) {
    console.error(`Cloudflare preview exited unexpectedly (code=${code}, signal=${signal}).`);
    process.exit(code ?? 1);
  }
});

let shuttingDown = false;
let proxy;

async function waitForPreview() {
  const deadline = Date.now() + 60_000;
  let lastError;

  while (Date.now() < deadline) {
    try {
      const response = await fetch(readyUrl, { redirect: "manual" });
      if (response.status >= 200 && response.status < 500) return;
      lastError = new Error(`preview returned HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }

  throw new Error(`Timed out waiting for Cloudflare preview: ${lastError ?? "unknown error"}`);
}

function shouldCompress(req, upstreamResponse, body) {
  if (req.method === "HEAD" || upstreamResponse.statusCode !== 200 || body.length < 50) return false;
  if (upstreamResponse.headers["content-encoding"]) return false;
  const contentType = String(upstreamResponse.headers["content-type"] || "");
  return compressibleContentType.test(contentType);
}

async function encodeForClient(req, body) {
  const accepted = String(req.headers["accept-encoding"] || "").toLowerCase();
  if (accepted.includes("br")) {
    return { body: await brotliCompressAsync(body), encoding: "br" };
  }
  if (accepted.includes("gzip")) {
    return { body: await gzipAsync(body), encoding: "gzip" };
  }
  return { body, encoding: null };
}

function copyHeaders(headers) {
  const copied = {};
  for (const [name, value] of Object.entries(headers)) {
    if (value === undefined) continue;
    const lower = name.toLowerCase();
    if (["content-length", "content-encoding", "transfer-encoding", "connection"].includes(lower)) continue;
    copied[name] = value;
  }
  return copied;
}

async function handleRequest(req, res) {
  const headers = { ...req.headers, host: `${upstreamHost}:${upstreamPort}`, "accept-encoding": "identity" };

  const upstreamRequest = http.request(
    {
      hostname: upstreamHost,
      port: upstreamPort,
      path: req.url,
      method: req.method,
      headers,
    },
    (upstreamResponse) => {
      const chunks = [];
      upstreamResponse.on("data", (chunk) => chunks.push(chunk));
      upstreamResponse.on("end", async () => {
        try {
          const originalBody = Buffer.concat(chunks);
          let responseBody = originalBody;
          let encoding = null;

          if (shouldCompress(req, upstreamResponse, originalBody)) {
            ({ body: responseBody, encoding } = await encodeForClient(req, originalBody));
          }

          const responseHeaders = copyHeaders(upstreamResponse.headers);
          if (encoding) {
            responseHeaders["content-encoding"] = encoding;
            responseHeaders.vary = responseHeaders.vary
              ? `${responseHeaders.vary}, Accept-Encoding`
              : "Accept-Encoding";
          }
          responseHeaders["content-length"] = String(responseBody.length);

          res.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.statusMessage, responseHeaders);
          if (req.method === "HEAD") res.end();
          else res.end(responseBody);
        } catch (error) {
          console.error("Compression proxy response failure:", error);
          if (!res.headersSent) res.writeHead(502, { "content-type": "text/plain" });
          res.end("Lighthouse preview proxy failure");
        }
      });
    },
  );

  upstreamRequest.on("error", (error) => {
    console.error("Compression proxy upstream failure:", error);
    if (!res.headersSent) res.writeHead(502, { "content-type": "text/plain" });
    res.end("Lighthouse preview upstream failure");
  });

  req.pipe(upstreamRequest);
}

async function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  if (proxy) await new Promise((resolve) => proxy.close(resolve));
  if (!preview.killed) preview.kill("SIGTERM");
  if (signal) process.exit(0);
}

process.on("SIGTERM", () => void shutdown("SIGTERM"));
process.on("SIGINT", () => void shutdown("SIGINT"));

try {
  await waitForPreview();
  proxy = http.createServer((req, res) => void handleRequest(req, res));
  await new Promise((resolve, reject) => {
    proxy.once("error", reject);
    proxy.listen(proxyPort, proxyHost, resolve);
  });
  console.log(`Lighthouse compression proxy ready at http://${proxyHost}:${proxyPort}`);
} catch (error) {
  console.error(error);
  await shutdown();
  process.exit(1);
}
