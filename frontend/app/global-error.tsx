/* eslint-disable @next/next/no-html-link-for-pages -- intentional full-page fallback navigation avoids loading the client Link runtime */
"use client";

export default function GlobalError({ error }: { error: Error & { digest?: string }; reset: () => void }) {
  const reference = error.digest
    ? `AMR-${error.digest.replace(/[^A-Za-z0-9-]/g, "").slice(0, 48).toUpperCase()}`
    : undefined;

  return (
    <html lang="en-ZA">
      <body style={{ margin: 0, background: "#07152d", color: "white", fontFamily: "Arial, sans-serif" }}>
        <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: "32px" }}>
          <section style={{ width: "min(680px, 100%)", textAlign: "center" }}>
            <div style={{ fontSize: "13px", fontWeight: 800, letterSpacing: ".18em", textTransform: "uppercase", color: "#ffcc66" }}>Amaris Mathematics Academy</div>
            <h1 style={{ margin: "18px 0 0", fontSize: "clamp(36px, 7vw, 64px)", lineHeight: 1.05 }}>We could not load this page.</h1>
            <p style={{ margin: "20px auto 0", maxWidth: "560px", fontSize: "18px", lineHeight: 1.7, color: "rgba(255,255,255,.72)" }}>Your information remains protected. Return to the academy home page and try again, or contact support if the problem continues.</p>
            <div style={{ marginTop: "28px", display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "12px" }}>
              <a href="/" style={{ borderRadius: "999px", background: "#ffcc66", color: "#07152d", padding: "13px 22px", fontWeight: 800, textDecoration: "none" }}>Return home</a>
              <a href="/contact" style={{ borderRadius: "999px", border: "1px solid rgba(255,255,255,.25)", color: "white", padding: "13px 22px", fontWeight: 700, textDecoration: "none" }}>Contact support</a>
            </div>
            {reference ? <p style={{ marginTop: "28px", fontSize: "12px", color: "rgba(255,255,255,.45)" }}>Support reference: {reference}</p> : null}
          </section>
        </main>
      </body>
    </html>
  );
}
