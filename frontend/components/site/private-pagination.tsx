import Link from "next/link";

export { paginatePrivateRows } from "@/lib/private-pagination";

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
        <Link prefetch={false} href={href(current - 1)} className="inline-flex min-h-11 items-center rounded-full border border-[#bfd0e8] px-4 font-semibold text-[#194f95]">Previous</Link>
      ) : <span className="min-h-11 px-4 py-3 text-[#60708a]">First page</span>}
      <span aria-live="polite" className="font-semibold text-[#263852]">Page {current} of {totalPages}</span>
      {current < totalPages ? (
        <Link prefetch={false} href={href(current + 1)} className="inline-flex min-h-11 items-center rounded-full bg-[#0b2a5b] px-4 font-semibold text-white">Next</Link>
      ) : <span className="min-h-11 px-4 py-3 text-[#60708a]">Last page</span>}
    </nav>
  );
}
