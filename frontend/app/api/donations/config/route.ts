import { NextRequest, NextResponse } from "next/server";
import { donationApiBase } from "@/lib/donation-api";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const base = donationApiBase(request.url);
  if (!base) return NextResponse.json({available:false, test_mode:false}, {headers:{"Cache-Control":"no-store"}});
  try {
    const response = await fetch(base+"/donations/config/",{cache:"no-store",signal:AbortSignal.timeout(7500)});
    if (!response.ok) throw new Error("Donation checkout not configured");
    const body = await response.json() as {available?:boolean,test_mode?:boolean};
    return NextResponse.json({available:body.available === true,test_mode:body.test_mode === true}, {headers:{"Cache-Control":"no-store"}});
  } catch {
    return NextResponse.json({available:false,test_mode:false}, {headers:{"Cache-Control":"no-store"}});
  }
}
