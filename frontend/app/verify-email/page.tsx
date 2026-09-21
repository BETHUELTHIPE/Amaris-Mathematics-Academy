import type { Metadata } from "next";
import Link from "next/link";
import { MailCheck } from "lucide-react";
import { resendVerificationAction, verifyEmailAction } from "@/app/auth/actions";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { ClearSafeFormDraft } from "@/components/site/safe-form-draft";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Verify Email" };

export default async function VerifyEmailPage({ searchParams }: { searchParams: Promise<{ email?: string; error?: string; registered?: string; resent?: string }> }) {
  const params = await searchParams;
  const email = params.email ?? "";
  const notice = params.resent ? "A new verification email has been sent. Please check your inbox and spam folder." : params.registered ? "Your profile was created. Check your email to verify it before logging in." : null;

  return <main className="min-h-screen bg-[#f5f7fb]"><ClearSafeFormDraft draftKey="student-registration-v1" /><Header /><section className="mx-auto max-w-xl px-5 py-16 lg:px-8 lg:py-24"><div className="rounded-[2rem] border border-[#dce4ef] bg-white p-7 text-center shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-10"><span className="mx-auto grid size-14 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]"><MailCheck className="size-7" /></span><p className="eyebrow mt-7">Email verification</p><h1 className="mt-4 text-4xl font-semibold tracking-[-.045em]">Check your inbox.</h1><p className="mt-4 text-base leading-7 text-[#60708a]">Enter the six-digit code sent to <strong className="text-[#263852]">{email || "your email address"}</strong>, or use the secure verification link in the email.</p>
    {params.error && <Alert variant="destructive" className="mt-6 text-left"><AlertDescription>{params.error}</AlertDescription></Alert>}
    {notice && <Alert className="mt-6 border-[#9fddce] bg-[#effbf7] text-left"><AlertDescription className="text-[#126854]">{notice}</AlertDescription></Alert>}
    <form action={verifyEmailAction} className="mt-8 grid justify-items-center gap-6">{email ? <input type="hidden" name="email" value={email} /> : <label className="grid w-full gap-2 text-left text-sm font-semibold">Email address<Input name="email" type="email" autoComplete="email" required /></label>}<label className="grid gap-2 text-sm font-semibold">Six-digit verification code<Input name="token" type="text" minLength={6} maxLength={6} inputMode="numeric" pattern="[0-9]{6}" autoComplete="one-time-code" required className="h-14 w-64 text-center text-2xl tracking-[.5em]" /></label><button type="submit" className="min-h-12 w-full rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white">Verify email</button></form>
    <form action={resendVerificationAction} className="mt-5">{email ? <input type="hidden" name="email" value={email} /> : <label className="mb-4 grid gap-2 text-left text-sm font-semibold">Email address for a new code<Input name="email" type="email" autoComplete="email" required /></label>}<button type="submit" className="text-sm font-bold text-[#1f5bbd] hover:underline">Send a new code</button></form><p className="mt-6 text-sm text-[#6a7890]">Already verified? <Link href="/login" className="font-bold text-[#1f5bbd]">Log in</Link></p></div></section><Footer /></main>;
}
