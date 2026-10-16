import { NextRequest, NextResponse } from "next/server";
import { donationApiBase, isValidDonationReference } from "@/lib/donation-api";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest, context: {params: Promise<{reference:string}>}) {
  const {reference} = await context.params;
  const headers = {"Cache-Control":"private, no-store"};
  if (!isValidDonationReference(reference)) return NextResponse.json({detail:"Invalid contribution reference."},{status:400,headers});
  const base = donationApiBase(request.url);
  if (!base) return NextResponse.json({detail:"Contribution status not available."},{status:503,headers});
  try {
    const response = await fetch(base+"/donations/"+encodeURIComponent(reference)+"/",
      {cache:"no-store",signal:AbortSignal.timeout(8000)});
    if (!response.ok) return NextResponse.json({detail:"Contribution status not available."},
      {status:response.status === 404?404:503,headers});
    const body = await response.json();
    return NextResponse.json(body,{status:200,headers});
  } catch {
    return NextResponse.json({detail:"Contribution status not available."},{status:503,headers});
  }
}
