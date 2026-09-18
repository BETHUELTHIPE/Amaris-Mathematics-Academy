import type { Metadata } from "next";
import Link from "next/link";
import { KeyRound } from "lucide-react";
import { forgotPasswordAction } from "@/app/auth/actions";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Forgot Password" };

export default async function ForgotPasswordPage({ searchParams }: { searchParams: Promise<{ error?: string; sent?: string }> }) {
  const params = await searchParams;
  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="mx-auto max-w-xl px-5 py-16 lg:px-8 lg:py-24"><div className="rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-10"><span className="grid size-14 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]"><KeyRound className="size-7" /></span><p className="eyebrow mt-7">Password recovery</p><h1 className="mt-4 text-4xl font-semibold tracking-[-.045em]">Reset your password.</h1><p className="mt-4 text-base leading-7 text-[#60708a]">Enter your registration email. If an account exists, we will send a secure reset link.</p>
    {params.error && <Alert variant="destructive" className="mt-6"><AlertDescription>{params.error}</AlertDescription></Alert>}
    {params.sent && <Alert className="mt-6 border-[#9fddce] bg-[#effbf7]" aria-live="polite"><AlertDescription className="text-[#126854]">If this email is registered, a secure password reset link has been requested. Check your inbox and spam or junk folder. If you do not receive it, you can submit the form again.</AlertDescription></Alert>}
    <form action={forgotPasswordAction} className="mt-7 grid gap-5"><label className="grid gap-2 text-sm font-semibold text-[#263852]">Email address<Input name="email" type="email" autoComplete="email" required className="h-12" /></label><button type="submit" className="min-h-12 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white">Send reset link now</button></form><p className="mt-6 text-center text-sm"><Link href="/login" className="font-bold text-[#1f5bbd]">Back to log in</Link></p></div></section><Footer /></main>;
}
