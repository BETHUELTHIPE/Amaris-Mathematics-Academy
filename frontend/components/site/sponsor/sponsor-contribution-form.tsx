"use client";

import { useState } from "react";
import { useFormStatus } from "react-dom";
import { ArrowRight, ShieldCheck, Wallet } from "lucide-react";
import type { SponsorDashboardData } from "@/lib/sponsor-api";

type Options = NonNullable<SponsorDashboardData["payment_options"]>;

function SubmitPayment({ enabled, preview }: { enabled: boolean; preview: boolean }) {
  const { pending } = useFormStatus();
  return <button type="submit" disabled={!enabled || pending || preview} className="sp-button sp-button-primary">{pending ? "Preparing checkout…" : preview ? "Design preview only" : "Continue to secure checkout"}<ArrowRight size={16} aria-hidden="true" /></button>;
}

export function SponsorContributionForm({ options, action, paymentKey, preview = false }: {
  options: Options; action?: (data: FormData) => Promise<void>; paymentKey?: string; preview?: boolean;
}) {
  const [provider, setProvider] = useState(options.find((item) => item.available)?.provider ?? "payfast");
  const selected = options.find((item) => item.provider === provider);
  const enabled = Boolean(selected?.available && action);
  return <section className="sp-panel sp-funding-panel" id="sponsor-payment-options">
    <div className="sp-panel-heading"><div><h2>Make a contribution</h2><p>Choose your amount and preferred payment provider.</p></div><Wallet size={22} aria-hidden="true" /></div>
    <form action={action} className="sp-funding-form">
      <input type="hidden" name="idempotency_key" value={paymentKey ?? ""} />
      <label className="sp-funding-amount">Contribution amount (ZAR)<span><strong>R</strong><input aria-label="Contribution amount in rand" name="amount" type="number" min="10" max="1000000" step="0.01" required placeholder="500.00" /></span><small>From R10.00</small></label>
      <fieldset><legend>Pay using</legend><div className="sp-payment-choices">{options.map((item) => <label key={item.provider} className={provider === item.provider ? "selected" : ""}><input type="radio" name="provider" value={item.provider} checked={provider === item.provider} disabled={!item.available} onChange={() => setProvider(item.provider)} /><span><strong>{item.label}</strong><small>{!item.available ? "Temporarily unavailable" : item.mode === "test" ? "Test checkout" : "Secure hosted payment"}</small></span></label>)}</div></fieldset>
      <div className="sp-funding-submit"><SubmitPayment enabled={enabled} preview={preview} /><p><ShieldCheck size={14} aria-hidden="true" />Funding updates after payment verification.</p></div>
      {!options.some((item) => item.available) && <p className="sp-small-note" role="status">Online contributions are currently unavailable. Contact Amaris to arrange your sponsorship.</p>}
      <p className="sp-funding-note">Already started a payment? Check its status in Contributions before starting another.</p>
    </form>
  </section>;
}
