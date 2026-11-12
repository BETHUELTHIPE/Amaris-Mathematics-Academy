import "server-only";
import { env } from "cloudflare:workers";
import { normalizeCmsApiBaseUrl } from "@/lib/cms-api-url";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { requireVerifiedStudent } from "@/lib/auth";

export type CurriculumSubscription = {
  reference: string; curriculum: string; curriculum_label: string; months: number;
  amount: string; currency: string; status: "pending" | "paid" | "refunded";
  gateway_mode: "sandbox" | "live"; starts_at: string | null; ends_at: string | null; active: boolean;
};
export type SubscriptionCheckout = { subscription: CurriculumSubscription; gateway_url: string; fields: Record<string, string> };
export async function subscriptionRequest(path = "", init: RequestInit = {}) {
  await requireVerifiedStudent("/dashboard/subscriptions");
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session?.access_token) throw new Error("Sign in to view your subscriptions.");
  const base = (env as unknown as { CMS_API_URL?: string }).CMS_API_URL || process.env.CMS_API_URL;
  if (!base) throw new Error("Subscription service is unavailable.");
  const response = await fetch(`${normalizeCmsApiBaseUrl(base)}/student/subscriptions/${path}`, {
    ...init, headers: { Accept: "application/json", "Content-Type": "application/json", Authorization: `Bearer ${data.session.access_token}` },
    cache: "no-store", signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new Error("Your subscription could not be loaded. Please try again shortly.");
  return response;
}
export async function getSubscriptions(): Promise<CurriculumSubscription[]> { return (await subscriptionRequest()).json(); }
export async function getSubscription(reference: string): Promise<CurriculumSubscription> {
  if (!/^SUB-[A-F0-9]{32}$/.test(reference)) throw new Error("Invalid subscription reference.");
  return (await subscriptionRequest(`${reference}/`)).json();
}
export async function createSubscriptionCheckout(curriculum: string, months: number): Promise<SubscriptionCheckout> {
  const student = await requireVerifiedStudent();
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${student.id}:${curriculum}:${months}:${new Date().toISOString().slice(0, 10)}`));
  const key = Array.from(new Uint8Array(digest)).map(value => value.toString(16).padStart(2, "0")).join("");
  const response = await subscriptionRequest("checkout/", { method: "POST", body: JSON.stringify({ curriculum, months, idempotency_key: key }) });
  const result = await response.json() as SubscriptionCheckout;
  if (!["https://www.payfast.co.za/eng/process", "https://sandbox.payfast.co.za/eng/process"].includes(result.gateway_url)
      || result.subscription.curriculum !== curriculum || result.subscription.months !== months
      || result.subscription.currency !== "ZAR" || result.fields.amount !== (months === 4 ? "3800.00" : "7600.00")) throw new Error("Subscription checkout details could not be verified.");
  return result;
}
