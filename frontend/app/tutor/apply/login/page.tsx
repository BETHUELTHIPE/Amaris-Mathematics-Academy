import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { GoogleAuthButton } from "@/components/site/google-auth-button";
import { getStudentIdentity } from "@/lib/auth";
import { loginApplicant } from "@/app/tutor/register/actions";
export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Tutor applicant sign in" };
export default async function ApplicantLogin({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const identity = await getStudentIdentity();
  if (identity?.emailVerified) redirect("/tutor/apply");
  const { error } = await searchParams;
  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="mx-auto max-w-xl px-5 py-14"><div className="rounded-3xl border border-[#dce4ef] bg-white p-8"><p className="eyebrow">Tutor applicant access</p><h1 className="mt-4 text-4xl font-semibold">Sign in to apply.</h1><p className="my-5 text-sm leading-7 text-[#60708a]">Use your verified Amaris account to submit qualifications and track your application.</p>{error && <p role="alert" className="mb-5 rounded-xl bg-red-50 p-4 text-red-900">{error}</p>}<GoogleAuthButton label="Continue with Google" next="/tutor/apply" /><form action={loginApplicant} className="mt-7 grid gap-5"><label className="grid gap-2 text-sm font-semibold">Email address<input name="email" required type="email" autoComplete="email" className="min-h-12 rounded-xl border border-[#cbd6e5] px-4" /></label><label className="grid gap-2 text-sm font-semibold">Password<input name="password" required type="password" autoComplete="current-password" className="min-h-12 rounded-xl border border-[#cbd6e5] px-4" /></label><button type="submit" className="min-h-12 rounded-full bg-[#0b2a5b] p-3 font-bold text-white">Sign in to your application</button></form><div className="mt-6 flex flex-wrap gap-5 text-sm font-semibold text-[#1f5bbd]"><Link href="/tutor/register">Register as an applicant</Link><Link href="/forgot-password">Forgot password?</Link><Link href="/tutor/verify-email">Verify email</Link></div></div></section><Footer /></main>;
}
