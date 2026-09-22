import { NextResponse, type NextRequest } from "next/server";
import { getSiteUrl } from "@/lib/supabase/config";
import { createStudentFileSignedUrl } from "@/lib/student-storage";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const path = request.nextUrl.searchParams.get("path");
  if (!path) {
    return NextResponse.redirect(new URL("/documents?error=File+path+is+missing.", getSiteUrl()));
  }

  try {
    const signedUrl = await createStudentFileSignedUrl(path);
    return NextResponse.redirect(signedUrl);
  } catch {
    return NextResponse.redirect(
      new URL("/documents?error=That+file+is+not+available+for+this+student.", getSiteUrl()),
    );
  }
}
