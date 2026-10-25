import "server-only";
import { cookies } from "next/headers";

/** Make the Next.js request cookie jar injectable for isolated auth action tests. */
export async function getPasswordRecoveryCookieStore() {
  return cookies();
}
