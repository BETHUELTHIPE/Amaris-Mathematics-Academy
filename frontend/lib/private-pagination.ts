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

