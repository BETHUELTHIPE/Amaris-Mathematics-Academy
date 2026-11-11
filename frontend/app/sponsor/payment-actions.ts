"use server";

import { redirect } from "next/navigation";
import { requireVerifiedStudent } from "@/lib/auth";
import { createSponsorCheckout, verifySponsorPayment } from "@/lib/sponsor-api";

export async function prepareSponsorPayment(formData: FormData): Promise<void> {
  await requireVerifiedStudent("/sponsor");
  let reference: string;
  try {
    const result = await createSponsorCheckout({
      amount: String(formData.get("amount") ?? ""),
      provider: String(formData.get("provider") ?? ""),
      idempotency_key: String(formData.get("idempotency_key") ?? ""),
    });
    if (!/^SC-[a-f0-9]{32}$/.test(result.reference)) throw new Error("Invalid payment reference");
    reference = result.reference;
  } catch {
    redirect("/sponsor?payment_error=checkout");
  }
  redirect(`/sponsor/payments/${encodeURIComponent(reference)}`);
}

export async function checkSponsorPayment(reference: string): Promise<void> {
  await requireVerifiedStudent("/sponsor");
  if (!/^SC-[a-f0-9]{32}$/.test(reference)) redirect("/sponsor");
  let pending = false;
  try { await verifySponsorPayment(reference); } catch { pending = true; }
  redirect(`/sponsor/payments/${encodeURIComponent(reference)}${pending ? "?verification=pending" : ""}`);
}
