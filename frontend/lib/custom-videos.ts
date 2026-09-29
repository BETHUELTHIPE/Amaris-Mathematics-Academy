import { env } from "cloudflare:workers";

export type CustomVideoOption = {
  value: string;
  label: string;
};

export type CustomVideoOptions = {
  enabled: boolean;
  pricing_configured: boolean;
  amount: string | null;
  currency: string;
  max_files: number;
  max_file_size_mb: number;
  curricula: CustomVideoOption[];
  subjects: CustomVideoOption[];
  grades: CustomVideoOption[];
  topic_mode: "free_text";
  modelled_topics: string[];
  topic_note: string;
};

const unavailable: CustomVideoOptions = {
  enabled: false,
  pricing_configured: false,
  amount: null,
  currency: "ZAR",
  max_files: 5,
  max_file_size_mb: 15,
  curricula: [],
  subjects: [],
  grades: [],
  topic_mode: "free_text",
  modelled_topics: [],
  topic_note: "Custom-video request options are temporarily unavailable.",
};

export async function getCustomVideoOptions(): Promise<CustomVideoOptions> {
  const workerBindings = env as unknown as { CMS_API_URL?: string };
  const base = (workerBindings.CMS_API_URL || process.env.CMS_API_URL)?.replace(
    /\/$/,
    "",
  );
  if (!base) return unavailable;

  try {
    const response = await fetch(`${base}/custom-video/options/`, {
      headers: { Accept: "application/json" },
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(4_000),
    });
    if (!response.ok) return unavailable;
    return (await response.json()) as CustomVideoOptions;
  } catch {
    return unavailable;
  }
}
