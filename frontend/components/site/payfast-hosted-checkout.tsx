import { CreditCard, ShieldCheck } from "lucide-react";
import { payFastHostedAction, type PayFastHostedPayload } from "@/lib/payfast-hosted-checkout";

/**
 * Progressive-enhancement checkout: always requires an explicit student click.
 * Browser navigates directly to the PayFast hosted screen via HTML form POST.
 * Never intercept this submit with fetch() or rely on client JavaScript.
 */
export function PayFastHostedCheckout({
  checkout,
  buttonLabel = "Continue to PayFast",
}: {
  checkout: PayFastHostedPayload;
  buttonLabel?: string;
}) {
  const action = payFastHostedAction(checkout);
  if (!action) {
    return (
      <div role="alert" className="mt-7 rounded-xl border border-[#f2d28d] bg-[#fff8e7] p-5 text-sm leading-6 text-[#765314]">
        Secure hosted payment is temporarily unavailable. No payment was started. Please try again later or contact Amaris support.
      </div>
    );
  }
  return (
    <div className="mt-7">
      <form method="post" action={action} target="_self" acceptCharset="UTF-8">
        {Object.entries(checkout.fields).map(([name, value]) => (
          <input key={name} name={name} type="hidden" value={value} />
        ))}
        <button type="submit" className="flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white hover:bg-[#123d79] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]">
          <CreditCard className="size-4" aria-hidden="true" /> {buttonLabel}
        </button>
      </form>
      <p className="mt-3 flex items-start justify-center gap-2 text-center text-xs leading-5 text-[#60708a]">
        <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        Selecting this button opens PayFast's secure hosted checkout in this tab. Your order remains pending until Amaris verifies PayFast's payment notification.
      </p>
    </div>
  );
}
