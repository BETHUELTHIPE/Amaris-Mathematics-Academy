/** Generic pending state; no tutor earnings or personal information until verified. */
export default function TutorDashboardLoading() {
  return (
    <main className="min-h-screen bg-[#f5f7fb]" role="status" aria-label="Loading secure tutor dashboard">
      <section className="bg-[#07152d] py-10">
        <div className="mx-auto max-w-7xl px-5" aria-hidden="true">
          <div className="h-4 w-36 rounded bg-white/15" />
          <div className="mt-6 h-10 w-64 max-w-full rounded-xl bg-white/15" />
          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            {Array.from({ length: 3 }, (_, index) => (
              <div key={index} className="h-28 rounded-2xl border border-white/15 bg-white/10" />
            ))}
          </div>
        </div>
      </section>
      <section className="mx-auto max-w-7xl px-5 py-8" aria-hidden="true">
        <div className="min-h-72 rounded-3xl border border-[#dce4ef] bg-white" />
      </section>
      <span className="sr-only">Verifying your tutor session</span>
    </main>
  );
}
