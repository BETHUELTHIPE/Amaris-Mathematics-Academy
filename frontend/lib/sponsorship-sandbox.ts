import { createHash, randomUUID } from "node:crypto";
import { sponsorshipAmount, sponsorshipMode } from "./sponsorship";

// PayFast's public shared sandbox account, also used by the Django payment service.
// Custom sandbox account overrides must be supplied together in server settings.
export function createSandboxSponsorship(amount: string, origin: string) {
  if (sponsorshipMode() !== "sandbox") throw new Error("Sandbox sponsorship is disabled.");
  const validatedAmount = sponsorshipAmount(amount);
  if (!validatedAmount) throw new Error("Choose an amount between R5 and R100,000 with at most two decimal places.");
  const configured = [process.env.PAYFAST_SPONSOR_SANDBOX_MERCHANT_ID, process.env.PAYFAST_SPONSOR_SANDBOX_MERCHANT_KEY, process.env.PAYFAST_SPONSOR_SANDBOX_PASSPHRASE];
  if (configured.some(Boolean) && !configured.every(Boolean)) throw new Error("Sandbox merchant settings must be configured together.");
  const fields: Record<string, string> = {
    merchant_id: configured[0] || "10000100",
    merchant_key: configured[1] || "46f0cd694581a",
    return_url: new URL("/sponsors/test-result?state=returned", origin).href,
    cancel_url: new URL("/sponsors/test-result?state=cancelled", origin).href,
    m_payment_id: `SP-TEST-${randomUUID()}`,
    amount: validatedAmount,
    item_name: "Amaris project sponsorship (sandbox test)",
  };
  // PayFast uses PHP urlencode conventions and an MD5 checksum, not URLSearchParams.
  const encode = (value: string) => encodeURIComponent(value.trim()).replace(/[!'()*]/g, char => `%${char.charCodeAt(0).toString(16).toUpperCase()}`).replace(/%20/g, "+");
  const signatureInput = Object.entries(fields).map(([key, value]) => `${key}=${encode(value)}`).join("&") + `&passphrase=${encode(configured[2] || "jt7NOE43FZPn")}`;
  fields.signature = createHash("md5").update(signatureInput).digest("hex");
  return { gatewayUrl: "https://sandbox.payfast.co.za/eng/process", fields };
}
