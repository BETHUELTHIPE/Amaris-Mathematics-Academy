import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { GoogleAuthButton } from "@/components/site/google-auth-button";
import { getStudentIdentity } from "@/lib/auth";
import { LocationFields } from "@/components/site/location-fields";
import { initialLocation } from "@/lib/location-server";
import type { LocationValues } from "@/lib/location-data";
import { registerApplicant } from "./actions";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Create a tutor applicant account" };
export default async function RegisterApplicantPage({ searchParams }: { searchParams: Promise<{ error?: string } & Partial<LocationValues>> }) {
  const identity = await getStudentIdentity();
  if (identity?.emailVerified) redirect("/tutor/apply");
  const params = await searchParams;
  const { error } = params;
  const location = await initialLocation(params);
  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="mx-auto max-w-xl px-5 py-14"><div className="rounded-3xl border border-[#dce4ef] bg-white p-7 sm:p-10"><p className="eyebrow">Tutor recruitment · Step 1</p><h1 className="mt-4 text-4xl font-semibold tracking-tight">Create your applicant account.</h1><p className="mt-5 text-sm leading-7 text-[#60708a]">Already have an Amaris account? <Link href="/tutor/apply/login" className="font-bold text-[#1f5bbd] underline">Sign in</Link> with the same email. After verifying your email, you will choose your available teaching dates, times and hours in the tutor application. Teaching access requires academy approval.</p>
    {error && <p role="alert" className="my-5 rounded-xl bg-red-50 p-4 text-red-900">{error}</p>}
    <div className="my-7"><GoogleAuthButton label="Register with Google" next="/tutor/apply" /></div><p className="mb-5 text-center text-sm text-[#60708a]">Or register with email</p>
    <form action={registerApplicant} className="grid gap-5">
      <Field name="firstName" label="First name" autoComplete="given-name" minLength={2} maxLength={80} />
      <Field name="lastName" label="Last name" autoComplete="family-name" minLength={2} maxLength={80} />
      <Field name="email" label="Email address" type="email" autoComplete="email" />
      <LocationFields initial={location} draftKey="tutor-application-v1" returnTo="/tutor/register" />
      <Field name="password" label="Password" type="password" autoComplete="new-password" minLength={12} maxLength={72} />
      <Field name="confirmPassword" label="Confirm password" type="password" autoComplete="new-password" minLength={12} maxLength={72} />
      <p className="text-sm leading-6 text-[#60708a]">Use 12–72 characters, with uppercase and lowercase letters, a number and a symbol.</p>
      <label className="flex gap-3 text-sm leading-6"><input name="consent" type="checkbox" required className="mt-1 size-5 shrink-0 accent-[#1f5bbd]" /><span>I agree to the <Link href="/terms" className="underline">Terms</Link> and <Link href="/privacy" className="underline">Privacy Policy</Link>.</span></label>
      <button type="submit" className="min-h-12 rounded-full bg-[#0b2a5b] p-3 font-bold text-white">Create applicant account</button>
    </form><Link href="/tutor/apply" className="mt-6 block text-sm font-semibold text-[#1f5bbd]">Back to tutor recruitment</Link>
  </div></section><Footer /></main>;
}
function Field({ name, label, ...props }: { name: string; label: string } & React.ComponentProps<"input">) {
  return <label className="grid gap-2 text-sm font-semibold">{label}<input {...props} name={name} required className="min-h-12 rounded-xl border border-[#cbd6e5] px-4" /></label>;
}
