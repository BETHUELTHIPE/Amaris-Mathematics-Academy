import { NextRequest, NextResponse } from "next/server";
import { donationApiBase, sameOrigin } from "@/lib/donation-api";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const headers = {"Cache-Control":"no-store"};
  if (!sameOrigin(request)) {
    return NextResponse.json({detail:"Cross-site contribution checkout is not permitted."},{status:403,headers});
  }
  const base = donationApiBase(request.url);
  if (!base) return NextResponse.json({detail:"Online contribution checkout is not configured."},{status:503,headers});
  try {
    const raw = await request.text();
    if (raw.length > 4096) return NextResponse.json({detail:"Contribution details are too long."},{status:400,headers});
    const body = JSON.parse(raw) as Record<string,unknown>;
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("Invalid form");
    const response = await fetch(base+"/donations/checkout/",{
      method:"POST", headers:{"Content-Type":"application/json","Accept":"application/json"},
      body:JSON.stringify(body), cache:"no-store", signal:AbortSignal.timeout(15000),
    });
    const result = await response.json().catch(()=>({})) as Record<string,unknown>;
    if (!response.ok) {
      return NextResponse.json({detail:typeof result.detail==="string"?result.detail:"Could not prepare contribution checkout."},
        {status:response.status === 429?429:response.status >= 500?503:400,headers});
    }
    if (typeof result.gateway_url !== "string" ||
       !["https://www.payfast.co.za/eng/process","https://sandbox.payfast.co.za/eng/process"].includes(result.gateway_url) ||
       typeof result.payment_reference !== "string" ||
       !result.payment_reference.startsWith("DON-") ||
       !result.fields || typeof result.fields !== "object") {
      throw new Error("Unexpected PayFast checkout");
    }
    return NextResponse.json(result,{status:201,headers});
  } catch {
    return NextResponse.json({detail:"Could not prepare contribution checkout. Please try again."},{status:503,headers});
  }
}
