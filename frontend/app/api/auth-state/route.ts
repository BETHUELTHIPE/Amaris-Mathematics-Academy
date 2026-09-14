import { NextResponse } from "next/server";
import { getStudentIdentity } from "@/lib/auth";

export async function GET() {
  const student = await getStudentIdentity();
  return NextResponse.json(
    {
      authenticated: Boolean(student),
      emailVerified: Boolean(student?.emailVerified),
    },
    {
      headers: {
        "Cache-Control": "private, no-store, max-age=0",
        Vary: "Cookie",
      },
    },
  );
}
