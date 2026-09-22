import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Check, LockKeyhole, ShieldCheck } from "lucide-react";
import { registerAction } from "@/app/auth/actions";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { getStudentIdentity } from "@/lib/auth";
import { SafeFormDraft } from "@/components/site/safe-form-draft";
import { GoogleAuthButton } from "@/components/site/google-auth-button";
import { LinkedInAuthButton } from "@/components/site/linkedin-auth-button";
import { FacebookAuthButton } from "@/components/site/facebook-auth-button";
import { GitHubAuthButton } from "@/components/site/github-auth-button";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Student Registration" };

const provinces = ["Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo", "Mpumalanga", "Northern Cape", "North West", "Western Cape"];
const levels = ["Grade 8", "Grade 9", "Grade 10", "Grade 11", "Grade 12", "TVET / College", "University", "Adult learner"];

export default async function RegisterPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const student = await getStudentIdentity();
  if (student?.emailVerified) redirect("/dashboard");
  const { error } = await searchParams;

  return <main className="min-h-screen bg-[#f5f7fb]">
    <Header />
    <section className="mx-auto grid max-w-7xl gap-10 px-5 py-12 lg:grid-cols-[.8fr_1.2fr] lg:items-start lg:px-8 lg:py-20">
      <div className="lg:sticky lg:top-36">
        <p className="eyebrow">Student registration</p>
        <h1 className="section-title mt-4">Create your private learning profile.</h1>
        <p className="mt-6 max-w-xl text-lg leading-8 text-[#60708a]">Register before enrolling. We verify your email so payments, courses and results stay connected to the correct student.</p>
        <div className="mt-8 grid gap-3">
          {["A private dashboard for your courses and progress", "Verified email before course access", "Secure password-based authentication", "Payment activation only after verification"].map((item) => <span key={item} className="flex items-center gap-3 text-sm font-medium text-[#3f4f67]"><span className="grid size-6 shrink-0 place-items-center rounded-full bg-[#daf5ec] text-[#16836d]"><Check className="size-3.5" /></span>{item}</span>)}
        </div>
        <div className="mt-8 flex items-start gap-3 rounded-2xl border border-[#dce4ef] bg-white p-5 text-sm leading-6 text-[#60708a]"><ShieldCheck className="mt-0.5 size-5 shrink-0 text-[#1f5bbd]" />Your password is handled by Supabase Auth and is never stored in the Amaris course database.</div>
      </div>
      <div className="rounded-[2rem] border border-[#dce4ef] bg-white p-6 shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-9">
        <div className="flex items-center gap-4"><span className="grid size-12 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]"><LockKeyhole className="size-6" /></span><div><h2 className="text-2xl font-semibold tracking-[-.03em]">Student details</h2><p className="mt-1 text-sm text-[#60708a]">All fields are required.</p></div></div>
        {error && <Alert variant="destructive" className="mt-6"><AlertDescription>{error}</AlertDescription></Alert>}
        <div className="mt-7 grid gap-3"><GoogleAuthButton label="Register with Google" /><LinkedInAuthButton label="Register with LinkedIn" /></div>
        <div className="my-7 flex items-center gap-4 text-xs font-bold uppercase tracking-[.12em] text-[#8a98ac]"><span className="h-px flex-1 bg-[#dce4ef]" /><span>or register with email</span><span className="h-px flex-1 bg-[#dce4ef]" /></div>
        <form action={registerAction} className="grid gap-5">
          <SafeFormDraft draftKey="student-registration-v1" allowedFields={["firstName", "lastName", "email", "mobile", "province", "academicLevel", "institution"]} />
          <div className="grid gap-5 sm:grid-cols-2"><AuthField label="First name" name="firstName" autoComplete="given-name" /><AuthField label="Last name" name="lastName" autoComplete="family-name" /></div>
          <div className="grid gap-5 sm:grid-cols-2"><AuthField label="Email address" name="email" type="email" autoComplete="email" /><AuthField label="Mobile number" name="mobile" type="tel" autoComplete="tel" placeholder="071 234 5678" /></div>
          <div className="grid gap-5 sm:grid-cols-2">
            <label className="grid gap-2 text-sm font-semibold text-[#263852]">Province<NativeSelect name="province" required className="h-12 w-full bg-white"><NativeSelectOption value="">Select province</NativeSelectOption>{provinces.map((province) => <NativeSelectOption key={province} value={province}>{province}</NativeSelectOption>)}</NativeSelect></label>
            <label className="grid gap-2 text-sm font-semibold text-[#263852]">Grade or academic level<NativeSelect name="academicLevel" required className="h-12 w-full bg-white"><NativeSelectOption value="">Select level</NativeSelectOption>{levels.map((level) => <NativeSelectOption key={level} value={level}>{level}</NativeSelectOption>)}</NativeSelect></label>
          </div>
          <AuthField label="School, college or university" name="institution" autoComplete="organization" />
          <div className="grid gap-5 sm:grid-cols-2"><AuthField label="Password" name="password" type="password" autoComplete="new-password" /><AuthField label="Confirm password" name="confirmPassword" type="password" autoComplete="new-password" /></div>
          <p className="-mt-2 text-xs leading-5 text-[#60708a]">Use 12–72 characters with uppercase, lowercase, a number and a symbol.</p>
          <label className="flex items-start gap-3 rounded-xl bg-[#f5f7fb] p-4 text-sm leading-6 text-[#52617a]"><input name="terms" type="checkbox" required className="mt-1 size-4 accent-[#1f5bbd]" /><span>I accept the <Link href="/terms" className="font-semibold text-[#1f5bbd] underline">Terms</Link> and <Link href="/privacy" className="font-semibold text-[#1f5bbd] underline">Privacy Policy</Link>.</span></label>
          <button type="submit" className="min-h-12 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white transition hover:bg-[#123d79]">Create student profile</button>
        </form>
        <p className="mt-6 text-center text-sm text-[#60708a]">Already registered? <Link href="/login" className="font-bold text-[#1f5bbd]">Log in</Link></p>
        <p className="mt-3 text-center text-sm text-[#60708a]"><Link href="/forgot-password" className="font-bold text-[#1f5bbd]">Reset your password</Link> or <Link href="/contact" className="font-bold text-[#1f5bbd]">contact us for help</Link>.</p>
      </div>
    </section>
    <Footer />
  </main>;
}

function AuthField({ label, name, type = "text", ...props }: { label: string; name: string; type?: string } & Omit<React.ComponentProps<typeof Input>, "name" | "type">) {
  return <label className="grid gap-2 text-sm font-semibold text-[#263852]">{label}<Input name={name} type={type} required className="h-12 bg-white" {...props} /></label>;
}
