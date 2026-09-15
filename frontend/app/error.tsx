"use client";

export default function ErrorPage({ error }: { error: Error & { digest?: string }; reset: () => void }) {
  const reference = error.digest
    ? `AMR-${error.digest.replace(/[^A-Za-z0-9-]/g, "").slice(0, 48).toUpperCase()}`
    : undefined;

  return (
    <main className="grid min-h-screen place-items-center bg-[#07152d] px-5 py-16 text-white">
      <section className="w-full max-w-2xl text-center">
        <p className="text-xs font-extrabold uppercase tracking-[.2em] text-[#ffcc66]">Amaris Mathematics Academy</p>
        <h1 className="mt-5 text-4xl font-semibold tracking-[-.045em] sm:text-6xl">We could not load this page.</h1>
        <p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-white/70">Your information remains protected. Return to the academy home page and try again, or contact support if the problem continues.</p>
        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <a href="/" className="rounded-full bg-[#ffcc66] px-6 py-3.5 font-bold text-[#07152d]">Return home</a>
          <a href="/contact" className="rounded-full border border-white/25 px-6 py-3.5 font-semibold text-white">Contact support</a>
        </div>
        {reference ? <p className="mt-8 text-xs text-white/45">Support reference: {reference}</p> : null}
      </section>
    </main>
  );
}
