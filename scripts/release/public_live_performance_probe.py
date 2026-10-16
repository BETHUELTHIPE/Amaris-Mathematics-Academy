"""Read-only public production latency and static compression probe.

No cookies, credentials, login endpoints or sensitive response bodies are logged.
Results are short-point-in-time samples from GitHub runner, not p75 RUM.
"""
import re
import statistics
import time
import urllib.error
import urllib.request

FRONTEND = "https://amaris-mathematics-academy-live-students.onrender.com"
BACKEND = "https://amaris-production-web.onrender.com"


def fetch(url, encoding="identity"):
    request = urllib.request.Request(
        url, headers={"User-Agent": "Amaris-public-performance-probe/1.0", "Accept-Encoding": encoding}
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=35) as reply:
        payload = reply.read()
        return reply.status, reply.headers, payload, (time.perf_counter() - started) * 1000


def probe(label, url):
    measures = []
    content = b""
    for index in range(4):
        status, headers, data, elapsed = fetch(url)
        if status != 200:
            raise RuntimeError(f"{label}: HTTP {status}")
        measures.append(round(elapsed))
        if index == 0:
            content = data
    print(f"PASS {label}: four full-response request samples ms={measures} median={statistics.median(measures):.1f}")
    return content


def main():
    html = probe("frontend homepage", FRONTEND + "/")
    probe("frontend announcements", FRONTEND + "/announcements")
    probe("backend health", BACKEND + "/health/")
    probe("public announcements API", BACKEND + "/api/v1/announcements/")

    paths = re.findall(rb'/_next/static/[A-Za-z0-9_./-]+[.]js', html)
    paths = [p.decode("ascii", "ignore") for p in paths]
    chosen = next((p for p in paths if "framework" in p), paths[0] if paths else "")
    if not chosen:
        print("WARN no JS path available in initial HTML; cannot compare real CDN compression")
        return
    for kind in ("identity", "br", "gzip"):
        status, headers, raw, duration = fetch(FRONTEND + chosen, encoding=kind)
        if status != 200:
            raise RuntimeError(f"static JS returned {status}")
        content_encoding = headers.get("Content-Encoding", "identity")
        vary = headers.get("Vary", "none")
        print(f"PASS static-JS accept={kind} served={content_encoding} bytes={len(raw)} ms={duration:.0f} vary={vary}")
    print("NOTE timings are GitHub-runner HTTP samples, not real-user Core Web Vitals")


if __name__ == "__main__":
    main()
