export default function SponsorLoading() {
  return <main className="min-h-screen bg-[#f5f7fb] p-8" aria-busy="true" aria-label="Loading sponsor dashboard">
    <div className="mx-auto max-w-6xl space-y-6"><p className="text-sm font-semibold text-[#31537e]" role="status">Loading your sponsor workspace…</p>
      <div className="h-40 rounded-3xl bg-[#e4eaf3] motion-safe:animate-pulse" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[1, 2, 3, 4].map((key) => <div key={key} className="h-32 rounded-2xl bg-[#e4eaf3] motion-safe:animate-pulse" />)}</div>
    </div>
  </main>;
}
