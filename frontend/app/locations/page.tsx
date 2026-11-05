import Link from "next/link";
import { redirect } from "next/navigation";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { LocationFields } from "@/components/site/location-fields";
import { initialLocation, parseLocation } from "@/lib/location-server";
import type { LocationValues } from "@/lib/location-data";

export const dynamic = "force-dynamic";
export const metadata = { title: "Choose your location" };
const allowed = new Set(["/register", "/tutor/register", "/tutor/apply", "/contact"]);
export default async function LocationPicker({ searchParams }: { searchParams: Promise<Partial<LocationValues> & { returnTo?: string; continue?: string }> }) {
  const params = await searchParams;
  const returnTo = params.returnTo && allowed.has(params.returnTo) ? params.returnTo : "/register";
  const initial = await initialLocation(params);
  let errors: string[] = [];
  if (params.continue === "1") {
    const parsed = await parseLocation(params);
    if (parsed.value) {
      const query = new URLSearchParams();
      for (const [field, value] of Object.entries(parsed.raw)) if (value) query.set(field, value);
      redirect(returnTo + "?" + query.toString());
    }
    errors = Object.values(parsed.errors);
  }
  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="mx-auto max-w-3xl px-5 py-12"><div className="rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-9">
    <h1 className="text-3xl font-semibold text-[#07152d]">Choose your location</h1>
    <p className="my-5 text-sm leading-7 text-[#52617a]">Choose your country, then update the choices. Choose a province or region and update again to see its cities. When all three fields are complete, continue to your form.</p>
    {errors.length > 0 && <ul role="alert" className="mb-5 list-inside list-disc text-sm text-[#b42318]">{errors.map(error => <li key={error}>{error}</li>)}</ul>}
    <form method="get" action="/locations" className="grid gap-5">
      <input type="hidden" name="returnTo" value={returnTo} />
      <LocationFields initial={initial} returnTo={returnTo} showPicker={false} />
      <button type="submit" formNoValidate className="min-h-12 rounded-full border border-[#cbd6e5] px-5 font-semibold text-[#0b2a5b]">Update province and city choices</button>
      <button type="submit" name="continue" value="1" className="min-h-12 rounded-full bg-[#0b2a5b] px-5 font-semibold text-white">Continue to form</button>
    </form><Link href={returnTo} className="mt-5 inline-block text-sm font-semibold text-[#1f5bbd] underline">Back to form</Link>
  </div></section><Footer /></main>;
}
