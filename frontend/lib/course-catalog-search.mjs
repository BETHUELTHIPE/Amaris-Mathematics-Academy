export const COURSE_PAGE_SIZE = 24;
export const COURSE_PROGRAMMES = ["All", "CAPS", "IEB", "TVET", "University"];
export const COURSE_SORTS = ["relevance", "price", "-price", "title", "-created_at"];

/** @param {Record<string, unknown>} [input] */
export function normalizeCatalogOptions(input = {}) {
  const query = typeof input.query === "string" ? input.query.normalize("NFKC").trim().replace(/\s+/g, " ").slice(0, 100) : "";
  const programmeInput = typeof input.programme === "string" ? input.programme.toLowerCase() : "";
  const programme = COURSE_PROGRAMMES.find(value => value.toLowerCase() === programmeInput) || "All";
  const level = typeof input.level === "string" ? input.level.trim().replace(/\s+/g, " ").slice(0, 100) : "";
  const sort = typeof input.sort === "string" && COURSE_SORTS.includes(input.sort) ? input.sort : "relevance";
  const requestedPage = typeof input.page === "string" || typeof input.page === "number" ? Number(input.page) : 1;
  const page = Number.isSafeInteger(requestedPage) && requestedPage >= 1 && requestedPage <= 100000 ? requestedPage : 1;
  const tokenText = query.replace(/\b(?:grade|gr)\.?\s*(\d{1,2})\b/gi, "grade$1").replace(/\bNC\s*\(\s*V\s*\)/gi, "ncv");
  const terms = [...new Set(tokenText.toLowerCase().match(/[\p{L}\p{N}]+/gu) || [])];
  const validationError = query && terms.length === 0 ? "Enter a topic, grade, curriculum or course name."
    : terms.length > 8 ? "Use no more than eight search words." : "";
  return { query, programme, level, sort, page, validationError };
}

/** @param {Record<string, unknown>} [input] */
export function catalogueHref(input = {}) {
  const { query, programme, level, sort, page } = normalizeCatalogOptions(input);
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (programme !== "All") params.set("programme", programme);
  if (level) params.set("level", level);
  if (sort !== "relevance") params.set("sort", sort);
  if (page > 1) params.set("page", String(page));
  return params.size ? `/courses?${params.toString()}` : "/courses";
}

/** @param {Record<string, unknown>} [input] */
export function catalogueApiPath(input = {}) {
  const { query, programme, level, sort, page } = normalizeCatalogOptions(input);
  const params = new URLSearchParams({ page: String(page), page_size: String(COURSE_PAGE_SIZE) });
  if (query) params.set("search", query);
  if (programme !== "All") params.set("programme", programme);
  if (level) params.set("academic_level", level);
  if (sort !== "relevance") params.set("ordering", sort);
  return `/courses/?${params.toString()}`;
}
