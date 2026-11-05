export type LiveClassSlot = {
  id: string;
  programme: "caps" | "ieb" | "tvet" | "university";
  programme_label: string;
  subject: "mathematics" | "mathematical_literacy";
  subject_label: string;
  level: string;
  tutor: string;
  starts_at: string;
  ends_at: string;
  duration_minutes: number;
  price: string;
  currency: string;
};

const cmsBaseUrl = process.env.CMS_API_URL?.replace(/\/$/, "");

export async function getLiveClassLevels(filters: {
  programme: string;
  subject: string;
}): Promise<string[]> {
  if (!cmsBaseUrl) return [];
  const query = new URLSearchParams({
    programme: filters.programme,
    subject: filters.subject,
  });
  try {
    const response = await fetch(
      `${cmsBaseUrl}/live-classes/levels/?${query.toString()}`,
      {
        headers: { Accept: "application/json" },
        next: { revalidate: 30 },
        signal: AbortSignal.timeout(4_000),
      },
    );
    if (!response.ok) return [];
    const data = (await response.json()) as unknown;
    const levels = data && typeof data === "object" && "levels" in data ? data.levels : [];
    return Array.isArray(levels) ? levels.filter((level): level is string => typeof level === "string") : [];
  } catch {
    return [];
  }
}

export async function getLiveClassSlots(filters: {
  programme?: string;
  subject?: string;
  level?: string;
  afterStart?: string;
  afterId?: string;
  limit?: number;
}): Promise<LiveClassSlot[]> {
  if (!cmsBaseUrl) return [];

  const query = new URLSearchParams();
  if (filters.programme) query.set("programme", filters.programme);
  if (filters.subject) query.set("subject", filters.subject);
  if (filters.level) query.set("level", filters.level);
  if (filters.afterStart && filters.afterId) {
    query.set("after_start", filters.afterStart);
    query.set("after_id", filters.afterId);
  }
  if (filters.limit) query.set("limit", String(Math.min(100, filters.limit)));

  try {
    const response = await fetch(
      `${cmsBaseUrl}/live-classes/slots/?${query.toString()}`,
      {
        headers: { Accept: "application/json" },
        next: { revalidate: 30 },
        signal: AbortSignal.timeout(4_000),
      },
    );
    if (!response.ok) return [];
    const data = (await response.json()) as unknown;
    return Array.isArray(data) ? (data as LiveClassSlot[]) : [];
  } catch {
    return [];
  }
}
