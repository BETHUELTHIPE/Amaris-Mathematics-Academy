import type { Metadata } from "next";
import Link from "next/link";
import { MailCheck } from "lucide-react";
import { sendLoginCodeAction, verifyLoginCodeAction } from "@/app/auth/actions";
import { safeRelativePath } from "@/lib/auth";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Email Code Sign In" };

export default async function EmailCodeLoginPage({
  searchParams,
}: {
  searchParams: Promise<{ email?: string; next?: string; error?: string; sent?: string }>;
}) {
  const params = await searchParams;
  const email = (params.email ?? "").trim().toLowerCase();
  const next = safeRelativePath(params.next);

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto max-w-xl px-5 py-16 lg:px-8 lg:py-24">
        <div className="min-w-0 rounded-[2rem] border border-[#dce4ef] bg-white p-6 text-center shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-10">
          <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]">
            <MailCheck className="size-7" />
          </span>
          <h1 className="mt-6 text-3xl font-semibold tracking-tight text-[#263852]">Enter your sign-in code</h1>
          <p className="mt-4 text-sm leading-6 text-[#60708a]">
            If this address belongs to a registered student, a six-digit code has been requested for{" "}
            <strong className="break-all text-[#263852]">{email || "your email address"}</strong>.
            Check your inbox and spam folder. Codes expire and can be used only once.
          </p>
          {params.error && <Alert variant="destructive" className="mt-6 text-left"><AlertDescription>{params.error}</AlertDescription></Alert>}
          <form action={verifyLoginCodeAction} className="mt-8 grid justify-items-center gap-6">
            <input type="hidden" name="email" value={email} />
            <input type="hidden" name="next" value={next} />
            <InputOTP name="token" maxLength={6} inputMode="numeric" pattern="[0-9]*" required aria-label="Six-digit sign-in code" containerClassName="max-w-full min-w-0 justify-center gap-0">
              <InputOTPGroup>{Array.from({ length: 6 }, (_, index) => <InputOTPSlot key={index} index={index} className="h-11 w-[clamp(1.75rem,7.5vw,3rem)] text-base sm:h-12 sm:w-12 sm:text-lg" />)}</InputOTPGroup>
            </InputOTP>
            <button type="submit" className="min-h-12 w-full rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white">Verify code and log in</button>
          </form>
          <form action={sendLoginCodeAction} className="mt-5">
            <input type="hidden" name="email" value={email} />
            <input type="hidden" name="next" value={next} />
            <button type="submit" className="text-sm font-bold text-[#1f5bbd] hover:underline">Request another code</button>
          </form>
          <p className="mt-7 text-sm text-[#60708a]">
            <Link href="/login" className="font-semibold text-[#1f5bbd]">Sign in with your password</Link>
            {" · "}
            <Link href="/verify-email" className="font-semibold text-[#1f5bbd]">Verify a new account</Link>
          </p>
        </div>
      </section>
      <Footer />
    </main>
  );
}
