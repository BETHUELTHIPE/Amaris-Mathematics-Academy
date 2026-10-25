import type { Metadata } from "next";
import Link from "next/link";
import { verifyRecoveryCodeAction } from "@/app/auth/actions";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Verify Your Password Reset",
  robots: { index: false, follow: false },
};

export default async function VerifyRecoveryPage({
  searchParams,
}: {
  searchParams: Promise<{ token_hash?: string; error?: string }>;
}) {
  const params = await searchParams;
  const tokenHash = params.token_hash && /^[A-Za-z0-9._-]{24,256}$/.test(params.token_hash)
    ? params.token_hash
    : null;
  return <main className="min-h-screen bg-[#f5f7fb]">
    <Header />
    <section className="mx-auto max-w-xl px-5 py-16 lg:px-8">
      <div className="rounded-3xl border border-[#dce4ef] bg-white p-7 shadow-lg sm:p-10">
        <p className="text-xs font-bold uppercase tracking-widest text-[#1f5bbd]">Amaris account recovery</p>
        <h1 className="mt-4 text-3xl font-semibold text-[#07152d]">Verify your password reset.</h1>
        <p className="mt-4 text-sm leading-7 text-[#60708a]">
          For your security, email links open this page without using your recovery code.
          Continue below, or enter the six-digit code from your latest Amaris email.
        </p>
        {params.error && <p role="alert" className="mt-5 rounded-xl bg-red-50 p-4 text-sm text-red-800">{params.error}</p>}
        {tokenHash && <form action={verifyRecoveryCodeAction} className="mt-7">
          <input type="hidden" name="token_hash" value={tokenHash} />
          <button type="submit" className="min-h-12 w-full rounded-full bg-[#0b2a5b] px-5 py-3 font-bold text-white">Continue to choose a new password</button>
        </form>}
        <div className="my-7 flex items-center gap-3 text-xs font-bold uppercase text-[#60708a]"><span className="h-px flex-1 bg-[#dce4ef]" />Or use your six-digit code<span className="h-px flex-1 bg-[#dce4ef]" /></div>
        <form action={verifyRecoveryCodeAction} className="grid gap-4">
          <label className="grid gap-2 text-sm font-semibold text-[#263852]">Registration email
            <input name="email" type="email" autoComplete="email" required className="min-h-12 rounded-xl border border-[#cbd6e5] px-4 font-normal" />
          </label>
          <label className="grid gap-2 text-sm font-semibold text-[#263852]">Six-digit recovery code
            <input name="token" type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required className="min-h-12 rounded-xl border border-[#cbd6e5] px-4 font-normal tracking-widest" />
          </label>
          <button type="submit" className="min-h-12 rounded-full bg-[#0b2a5b] px-5 py-3 font-bold text-white">Verify code and reset password</button>
        </form>
        <p className="mt-6 text-sm text-[#60708a]">Need another email? <Link href="/forgot-password" className="font-semibold text-[#1f5bbd] underline">Request a new reset code</Link>.</p>
      </div>
    </section>
    <Footer />
  </main>;
}
