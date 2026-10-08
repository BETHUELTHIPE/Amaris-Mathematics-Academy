export type VideoRequestPackage = {
  value: "chapter_topic" | "previous_assignment" | "previous_exam" | "complete_content";
  label: string;
  amount: string;
  currency: "ZAR";
};

const fallbackPackages: VideoRequestPackage[] = [
  { value: "chapter_topic", label: "Chapter or topic video", amount: "450.00", currency: "ZAR" },
  { value: "previous_assignment", label: "Previous assignment walkthrough", amount: "450.00", currency: "ZAR" },
  { value: "previous_exam", label: "Previous exam walkthrough", amount: "1800.00", currency: "ZAR" },
  { value: "complete_content", label: "Complete subject content", amount: "1800.00", currency: "ZAR" },
];

export async function getVideoRequestPackages(): Promise<VideoRequestPackage[]> {
  const baseUrl = process.env.CMS_API_URL?.replace(/\/$/, "");
  if (!baseUrl) return fallbackPackages;
  try {
    const response = await fetch(`${baseUrl}/video-requests/packages/`, {
      headers: { Accept: "application/json" },
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(4_000),
    });
    if (!response.ok) return fallbackPackages;
    const data = (await response.json()) as unknown;
    return Array.isArray(data) && data.length > 0
      ? (data as VideoRequestPackage[])
      : fallbackPackages;
  } catch {
    return fallbackPackages;
  }
}

