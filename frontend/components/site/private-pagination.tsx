import Link from "next/link";

/** Pure in-memory pagination of an already-authorized, per-request result.
 * It does NOT change API permissions or cache any student's/tutor's data.
 */
export function paginatePrivateRows<T>(
  records: readonly T[],
  rawPage: string | undefined,
  perPage: number,
): { rows: T[]; current: number; totalPages: number; count: number } {
  if (!Number.isSafeInteger(perPage) || perPage < 1 || perPage > 100) {
    throw new RangeError("Invalid private dashboard page size");
  }
  const totalPages = Math.max(1, Math.ceil(records.length / perPage));
  // Reject signed/scientific/fractional, excessive and malformed user input.
  const parsed = rawPage && /^[1-9][0-9]{0,5}$/.test(rawPage) ? Number(rawPage) : 1;
  const current = Math.min(parsed, totalPages);
  const first = (current - 1) * perPage;
  return {
    rows: records.slice(first, first + perPage),
    current,
    totalPages,
    count: records.length,
  };
}

type PrivatePaginationProps = {
  basePath: string;
  queryKey: "page" | "courses_page" | "videos_page" | "slots_page" | "bookings_page";
  anchor: string;
  current: number;
  totalPages: number;
  preserve?: Partial<Record<"courses_page" | "videos_page" | "slots_page" | "bookings_page", number>>;
};

export function PrivatePagination({
  basePath, queryKey, anchor, current, totalPages, preserve = {},
}: PrivatePaginationProps) {
  if (totalPages < 2) return null;
  function href(page: number) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(preserve)) {
      if (Number.isSafeInteger(value) && value > 1) params.set(key, String(value));
    }
    params.set(queryKey, String(page));
    return `${basePath}?${params.toString()}#${anchor}`;
  }
  return (
    <nav aria-label="List pages" className="mt-5 flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-xl border border-[#dce4ef] bg-white px-4 py-3 text-sm">
      {current > 1 ? (
        <Link href={href(current - 1)} className="inline-flex min-h-11 items-center rounded-full border border-[#bfd0e8] px-4 font-semibold text-[#194f95]">Previous</Link>
      ) : <span className="min-h-11 px-4 py-3 text-[#60708a]">First page</span>}
      <span aria-live="polite" className="font-semibold text-[#263852]">Page {current} of {totalPages}</span>
      {current < totalPages ? (
        <Link href={href(current + 1)} className="inline-flex min-h-11 items-center rounded-full bg-[#0b2a5b] px-4 font-semibold text-white">Next</Link>
      ) : <span className="min-h-11 px-4 py-3 text-[#60708a]">Last page</span>}
    </nav>
  );
}
