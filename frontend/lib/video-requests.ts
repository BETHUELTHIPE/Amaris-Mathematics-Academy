export type VideoRequestOption = { value: string; label: string };

export type VideoRequestOptions = {
  programmes: VideoRequestOption[];
  subjects: VideoRequestOption[];
  school_levels: string[];
  caps_mathematics_topics: string[];
  topic_source: "free_text";
  topic_notice: string;
  price: string | null;
  currency: string;
  checkout_enabled: boolean;
  max_files: number;
  max_file_size_mb: number;
};

const cmsBaseUrl = process.env.CMS_API_URL?.replace(/\/$/, "");

const fallbackOptions: VideoRequestOptions = {
  programmes: [
    { value: "caps", label: "CAPS" },
    { value: "ieb", label: "IEB" },
    { value: "tvet", label: "TVET" },
    { value: "university", label: "University" },
  ],
  subjects: [
    { value: "mathematics", label: "Mathematics" },
    { value: "mathematical_literacy", label: "Mathematical Literacy" },
  ],
  school_levels: ["Grade 10", "Grade 11", "Grade 12"],
  caps_mathematics_topics: [],
  topic_source: "free_text",
  topic_notice:
    "Formal CAPS Learning Outcome / Assessment Standard topics are not modelled in the current content database. Enter the topic from your source material and upload the supporting document.",
  price: null,
  currency: "ZAR",
  checkout_enabled: false,
  max_files: 5,
  max_file_size_mb: 20,
};

export async function getVideoRequestOptions(): Promise<VideoRequestOptions> {
  if (!cmsBaseUrl) return fallbackOptions;
  try {
    const response = await fetch(`${cmsBaseUrl}/custom-videos/options/`, {
      headers: { Accept: "application/json" },
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(4_000),
    });
    if (!response.ok) return fallbackOptions;
    return (await response.json()) as VideoRequestOptions;
  } catch {
    return fallbackOptions;
  }
}
