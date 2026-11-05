import http from "node:http";
import { createBrotliCompress, createGzip } from "node:zlib";

const upstreamHost = process.env.LIGHTHOUSE_UPSTREAM_HOST ?? "127.0.0.1";
const upstreamPort = Number(process.env.LIGHTHOUSE_UPSTREAM_PORT ?? "4173");
const listenHost = process.env.LIGHTHOUSE_PROXY_HOST ?? "127.0.0.1";
const listenPort = Number(process.env.LIGHTHOUSE_PROXY_PORT ?? "4180");

function isCompressible(contentType = "") {
  return /^(text\/|application\/(javascript|json|xml|wasm)|image\/svg\+xml)/i.test(
    contentType,
  );
}

const server = http.createServer((request, response) => {
  const headers = { ...request.headers };
  delete headers["accept-encoding"];
  headers.host = `${upstreamHost}:${upstreamPort}`;

  const upstream = http.request(
    {
      hostname: upstreamHost,
      port: upstreamPort,
      path: request.url,
      method: request.method,
      headers,
    },
    (upstreamResponse) => {
      const responseHeaders = { ...upstreamResponse.headers };
      delete responseHeaders["content-length"];
      delete responseHeaders["content-encoding"];

      const contentType = String(upstreamResponse.headers["content-type"] ?? "");
      const accepted = String(request.headers["accept-encoding"] ?? "");
      let compressor = null;

      if (isCompressible(contentType) && accepted.includes("br")) {
        responseHeaders["content-encoding"] = "br";
        compressor = createBrotliCompress();
      } else if (isCompressible(contentType) && accepted.includes("gzip")) {
        responseHeaders["content-encoding"] = "gzip";
        compressor = createGzip();
      }

      responseHeaders.vary = responseHeaders.vary
        ? `${responseHeaders.vary}, Accept-Encoding`
        : "Accept-Encoding";

      response.writeHead(upstreamResponse.statusCode ?? 502, responseHeaders);
      if (compressor) {
        upstreamResponse.pipe(compressor).pipe(response);
      } else {
        upstreamResponse.pipe(response);
      }
    },
  );

  upstream.on("error", (error) => {
    if (!response.headersSent) {
      response.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
    }
    response.end(`Preview upstream unavailable: ${error.message}`);
  });

  request.pipe(upstream);
});

server.listen(listenPort, listenHost, () => {
  console.log(
    `Lighthouse production-like proxy ready at http://${listenHost}:${listenPort}`,
  );
});

for (const signal of ["SIGTERM", "SIGINT"]) {
  process.on(signal, () => {
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 5000).unref();
  });
}
