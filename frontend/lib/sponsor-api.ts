import { env } from "cloudflare:workers";
import { normalizeCmsApiBaseUrl } from "@/lib/cms-api-url";
import { requireVerifiedStudent } from "@/lib/auth";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export type SponsorLearner = {
  id: string;
  learner_label: string;
  programme: string;
  programme_label: string;
  level: string;
  amount: string;
  status: "planned" | "active" | "completed" | "cancelled";
  starts_on: string;
  ends_on: string | null;
  progress_percent: number | null;
  progress_updated_at: string | null;
};

export type SponsorDashboardData = {
  sponsor: { name: string; organisation: string; annual_target: string };
  summary: {
    received: string; pledged: string; allocated: string; balance: string;
    students_supported: number; active_students: number; current_year_received: string;
  };
  currency: "ZAR";
  as_of: string;
  year: number;
  monthly_contributions: { month: string; amount: string }[];
  programme_allocations: { programme: string; amount: string }[];
  learners: SponsorLearner[];
  contributions: { reference: string; amount: string; status: "pledged" | "received" | "refunded"; date: string; description: string }[];
  learners_total: number;
  contributions_total: number;
  page: number;
  page_size: number;
};

export class SponsorApiError extends Error {
  constructor(public readonly status: number) {
    super("Sponsor information could not be loaded.");
  }
}

async function sponsorFetch(path: string): Promise<Response> {
  await requireVerifiedStudent("/sponsor");
  const { data, error } = await (await createSupabaseServerClient()).auth.getSession();
  const token = data.session?.access_token;
  if (error || !token) throw new SponsorApiError(401);
  const bindings = env as unknown as { CMS_API_URL?: string };
  const base = bindings.CMS_API_URL || process.env.CMS_API_URL;
  if (!base) throw new SponsorApiError(503);
  const response = await fetch(`${normalizeCmsApiBaseUrl(base)}${path}`, {
    headers: { Authorization: `Bearer ${token}`, Accept: path.includes("statement") ? "text/csv" : "application/json" },
    cache: "no-store",
    signal: AbortSignal.timeout(8_000),
    redirect: "error",
  });
  if (!response.ok) throw new SponsorApiError(response.status);
  return response;
}

export async function getSponsorDashboard(year?: string, page?: string): Promise<SponsorDashboardData> {
  const query = new URLSearchParams();
  if (year) query.set("year", year);
  if (page) query.set("page", page);
  return (await sponsorFetch(`/sponsor/dashboard/?${query}`)).json() as Promise<SponsorDashboardData>;
}

export async function getSponsorStatement(year?: string): Promise<Response> {
  const query = new URLSearchParams();
  if (year) query.set("year", year);
  return sponsorFetch(`/sponsor/statement/?${query}`);
}
