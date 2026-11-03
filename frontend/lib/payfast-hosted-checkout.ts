/**
 * Browser-hosted PayFast is a top-level, user-submitted HTML POST, not a
 * fetch(), iframe, GET redirect or an in-page card collection form.
 *
 * Treat checkout payloads received from Django as untrusted until the gateway
 * origin and required signed fields have been checked. A gateway mismatch must
 * fail closed rather than open an arbitrary URL with signed payment details.
 */
export type PayFastHostedPayload = {
  gateway_url: string;
  fields: Record<string, string>;
};

const GATEWAYS = new Set([
  "https://sandbox.payfast.co.za/eng/process",
  "https://www.payfast.co.za/eng/process",
]);

export function payFastHostedAction(payload: PayFastHostedPayload): string | null {
  if (!GATEWAYS.has(payload.gateway_url)) return null;
  const fields = payload.fields;
  if (!fields || typeof fields !== "object" || Array.isArray(fields)) return null;

  for (const name of ["merchant_id", "merchant_key", "m_payment_id", "item_name", "amount", "signature", "return_url", "cancel_url", "notify_url"]) {
    if (typeof fields[name] !== "string" || !fields[name].trim()) return null;
  }
  if (!/^[a-f0-9]{32}$/i.test(fields.signature)) return null;
  if (!/^\d{1,8}\.\d{2}$/.test(fields.amount) || Number(fields.amount) <= 0) return null;
  if (fields.m_payment_id.length > 100 || fields.item_name.length > 100) return null;
  // The provider cannot send authoritative ITNs back to an HTTP endpoint.
  for (const name of ["return_url", "cancel_url", "notify_url"]) {
    try {
      const url = new URL(fields[name]);
      if (url.protocol !== "https:" || !url.hostname || url.username || url.password) return null;
    } catch {
      return null;
    }
  }
  for (const [name, value] of Object.entries(fields)) {
    if (!/^[a-z][a-z0-9_]{0,63}$/.test(name) || typeof value !== "string" || value.length > 2048) return null;
  }
  return payload.gateway_url;
}
