import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { CheckCircle2, LayoutDashboard } from "lucide-react";
import { loginAction } from "@/app/auth/actions";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { getStudentIdentity, safeRelativePath } from "@/lib/auth";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Student Log In" };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ error?: string; next?: string; password_updated?: string; signed_out?: string }> }) {
  const student = await getStudentIdentity();
  if (student?.emailVerified) redirect("/dashboard");
  const params = await searchParams;
  const next = safeRelativePath(params.next);
  const success = params.password_updated ? "Your password has been updated. Log in with your new password." : params.signed_out ? "You have signed out securely." : null;

  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="mx-auto max-w-xl px-5 py-16 lg:px-8 lg:py-24"><div className="rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-10"><span className="grid size-14 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]"><LayoutDashboard className="size-7" /></span><p className="eyebrow mt-7">Student access</p><h1 className="mt-4 text-4xl font-semibold tracking-[-.045em]">Welcome back.</h1><p className="mt-4 text-base leading-7 text-[#60708a]">Log in to continue lessons and view your private learning dashboard.</p>
    {params.error && <Alert variant="destructive" className="mt-6"><AlertDescription>{params.error}</AlertDescription></Alert>}
    {success && <Alert className="mt-6 border-[#9fddce] bg-[#effbf7] text-[#126854]"><CheckCircle2 /><AlertDescription className="text-[#126854]">{success}</AlertDescription></Alert>}
    <form action={loginAction} className="mt-7 grid gap-5"><input type="hidden" name="next" value={next} /><label className="grid gap-2 text-sm font-semibold text-[#263852]">Email address<Input name="email" type="email" autoComplete="email" required className="h-12" /></label><label className="grid gap-2 text-sm font-semibold text-[#263852]"><span className="flex items-center justify-between gap-4">Password<Link href="/forgot-password" className="text-xs font-bold text-[#1f5bbd]">Forgot password?</Link></span><Input name="password" type="password" autoComplete="current-password" required className="h-12" /></label><button type="submit" className="min-h-12 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white transition hover:bg-[#123d79]">Log in securely</button></form>
    <p className="mt-6 text-center text-sm text-[#69778f]">New to Amaris? <Link href="/register" className="font-bold text-[#1f5bbd]">Create your profile</Link></p></div></section><Footer /></main>;
}
