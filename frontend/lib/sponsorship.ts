/** Public, merchant-owned PayFast payment link; never store merchant secrets here. */
export function getSponsorshipPaymentUrl(value = process.env.PAYFAST_SPONSOR_URL): string | null {
  if (!value?.trim()) return null;
  try {
    const url = new URL(value.trim());
    const allowedHosts = new Set(["payfast.co.za", "www.payfast.co.za", "payment.payfast.io"]);
    if (url.protocol !== "https:" || !allowedHosts.has(url.hostname) || url.username || url.password || url.port || url.pathname === "/") return null;
    return url.href;
  } catch {
    return null;
  }
}

export function sponsorshipMode(value = process.env.PAYFAST_SPONSOR_MODE): "sandbox" | "live" {
  return value === "live" ? "live" : "sandbox";
}

export function sponsorshipAmount(value: unknown): string | null {
  if (typeof value !== "string" || !/^\d{1,6}(\.\d{1,2})?$/.test(value)) return null;
  const cents = Math.round(Number(value) * 100);
  return cents >= 500 && cents <= 10000000 ? (cents / 100).toFixed(2) : null;
}
