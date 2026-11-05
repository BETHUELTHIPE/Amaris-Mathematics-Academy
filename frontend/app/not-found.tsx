/* eslint-disable @next/next/no-html-link-for-pages */

export default function NotFound() {
  return (
    <main className="grid min-h-screen place-items-center bg-[#07152d] px-5 py-16 text-white">
      <section className="w-full max-w-2xl text-center">
        <p className="text-xs font-extrabold uppercase tracking-[.2em] text-[#ffcc66]">Amaris Mathematics Academy</p>
        <p className="mt-6 font-mono text-6xl font-semibold tracking-[-.06em] text-white/20">404</p>
        <h1 className="mt-5 text-4xl font-semibold tracking-[-.045em] sm:text-6xl">We could not find that page.</h1>
        <p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-white/70">
          The address may have changed or the page may no longer be available. Your account and payment information are unaffected.
        </p>
        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <a href="/" className="rounded-full bg-[#ffcc66] px-6 py-3.5 font-bold text-[#07152d]">Return home</a>
          <a href="/courses" className="rounded-full border border-white/25 px-6 py-3.5 font-semibold text-white">Browse courses</a>
          <a href="/contact" className="rounded-full border border-white/25 px-6 py-3.5 font-semibold text-white">Contact support</a>
        </div>
      </section>
    </main>
  );
}
