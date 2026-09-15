import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { LockKeyhole } from "lucide-react";
import { resetPasswordAction } from "@/app/auth/actions";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { getStudentIdentity } from "@/lib/auth";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Choose New Password", robots: { index: false, follow: false } };

export default async function ResetPasswordPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const student = await getStudentIdentity();
  if (!student) redirect("/forgot-password?error=Your%20reset%20link%20has%20expired.%20Request%20a%20new%20one.");
  const params = await searchParams;
  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="mx-auto max-w-xl px-5 py-16 lg:px-8 lg:py-24"><div className="rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-10"><span className="grid size-14 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]"><LockKeyhole className="size-7" /></span><p className="eyebrow mt-7">Account security</p><h1 className="mt-4 text-4xl font-semibold tracking-[-.045em]">Choose a new password.</h1><p className="mt-4 text-sm leading-7 text-[#60708a]">Use 12–72 characters with uppercase, lowercase, a number and a symbol. All existing sessions will be signed out after the change.</p>
    {params.error && <Alert variant="destructive" className="mt-6"><AlertDescription>{params.error}</AlertDescription></Alert>}
    <form action={resetPasswordAction} className="mt-7 grid gap-5"><label className="grid gap-2 text-sm font-semibold text-[#263852]">New password<Input name="password" type="password" autoComplete="new-password" required className="h-12" /></label><label className="grid gap-2 text-sm font-semibold text-[#263852]">Confirm new password<Input name="confirmPassword" type="password" autoComplete="new-password" required className="h-12" /></label><button type="submit" className="min-h-12 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white">Update password</button></form></div></section><Footer /></main>;
}
