const DEFAULT_SITE_URL =
  "https://amaris-mathematics-academy-live-students.onrender.com";

function readEnvironmentValue(key: string): string | undefined {
  if (typeof process !== "undefined") {
    const processValue = process.env[key];
    if (processValue) return processValue;
  }

  return undefined;
}

export function getSupabaseConfig(): {
  url: string;
  publishableKey: string;
} | null {
  const url = readEnvironmentValue("SUPABASE_URL");
  const publishableKey = readEnvironmentValue("SUPABASE_PUBLISHABLE_KEY");

  if (!url || !publishableKey) return null;
  return { url, publishableKey };
}

export function requireSupabaseConfig() {
  const config = getSupabaseConfig();
  if (!config) {
    throw new Error("Student authentication is not configured.");
  }
  return config;
}

export function getSiteUrl(): string {
  return (readEnvironmentValue("SITE_URL") ?? DEFAULT_SITE_URL).replace(
    /\/$/,
    "",
  );
}
