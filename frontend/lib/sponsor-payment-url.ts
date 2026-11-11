export function validSponsorGatewayUrl(provider: string, value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password && !url.hash &&
      (provider === "paystack" ? url.host === "checkout.paystack.com" && url.pathname.length > 1
        : provider === "payfast" && ["sandbox.payfast.co.za", "www.payfast.co.za"].includes(url.host) && url.pathname === "/eng/process");
  } catch { return false; }
}
