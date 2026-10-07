export type VideoRequestOption = {
  value: string;
  label: string;
};

export type VideoRequestInfo = {
  price: string;
  currency: string;
  programmes: VideoRequestOption[];
  subjects: VideoRequestOption[];
};

const cmsBaseUrl = process.env.CMS_API_URL?.replace(/\/$/, "");

const FALLBACK_INFO: VideoRequestInfo = {
  price: "150.00",
  currency: "ZAR",
  programmes: [],
  subjects: [],
};

/**
 * Public pricing + option metadata. The browser never owns the price;
 * it only renders what the server declares.
 */
export async function getVideoRequestInfo(): Promise<VideoRequestInfo> {
  if (!cmsBaseUrl) return FALLBACK_INFO;

  try {
    const response = await fetch(`${cmsBaseUrl}/video-requests/info/`, {
      headers: { Accept: "application/json" },
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(4_000),
    });
    if (!response.ok) return FALLBACK_INFO;
    const data = (await response.json()) as Partial<VideoRequestInfo> | null;
    if (!data || typeof data.price !== "string") return FALLBACK_INFO;
    return {
      price: data.price,
      currency: data.currency ?? "ZAR",
      programmes: Array.isArray(data.programmes) ? data.programmes : [],
      subjects: Array.isArray(data.subjects) ? data.subjects : [],
    };
  } catch {
    return FALLBACK_INFO;
  }
}
