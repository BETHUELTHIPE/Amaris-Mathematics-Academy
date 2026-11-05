/** Generic pending state: renders before identity verification and exposes no private data. */
export default function StudentDashboardLoading() {
  return (
    <main className="min-h-screen bg-[#f5f7fb]" role="status" aria-label="Loading secure student dashboard">
      <section className="border-b border-[#dce4ef] bg-white">
        <div className="mx-auto max-w-7xl px-5 py-10" aria-hidden="true">
          <div className="h-4 w-32 rounded bg-[#edf1f6]" />
          <div className="mt-5 h-10 w-64 max-w-full rounded-xl bg-[#edf1f6]" />
        </div>
      </section>
      <div className="mx-auto grid max-w-7xl gap-5 px-5 py-8 lg:grid-cols-[240px_minmax(0,1fr)]" aria-hidden="true">
        <div className="h-56 rounded-2xl border border-[#dce4ef] bg-white" />
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 4 }, (_, index) => (
            <div key={index} className="min-h-32 rounded-2xl border border-[#dce4ef] bg-white p-6">
              <div className="h-5 w-24 rounded bg-[#edf1f6]" />
              <div className="mt-5 h-9 w-20 rounded bg-[#edf1f6]" />
            </div>
          ))}
        </div>
      </div>
      <span className="sr-only">Verifying your student session</span>
    </main>
  );
}
