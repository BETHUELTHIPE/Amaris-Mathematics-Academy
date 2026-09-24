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

export async function getLiveClassSlots(filters: {
  programme?: string;
  subject?: string;
  level?: string;
}): Promise<LiveClassSlot[]> {
  if (!cmsBaseUrl) return [];

  const query = new URLSearchParams();
  if (filters.programme) query.set("programme", filters.programme);
  if (filters.subject) query.set("subject", filters.subject);
  if (filters.level) query.set("level", filters.level);

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
