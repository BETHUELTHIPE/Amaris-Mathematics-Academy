import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { ShieldCheck } from "lucide-react";
import { completeGoogleProfileAction } from "@/app/auth/actions";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { getStudentIdentity, safeRelativePath } from "@/lib/auth";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Complete Student Profile" };

const provinces = [
  "Eastern Cape",
  "Free State",
  "Gauteng",
  "KwaZulu-Natal",
  "Limpopo",
  "Mpumalanga",
  "Northern Cape",
  "North West",
  "Western Cape",
];

const levels = [
  "Grade 8",
  "Grade 9",
  "Grade 10",
  "Grade 11",
  "Grade 12",
  "TVET / College",
  "University",
  "Adult learner",
];

export default async function CompleteProfilePage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; next?: string }>;
}) {
  const student = await getStudentIdentity();
  const params = await searchParams;
  const next = safeRelativePath(params.next);

  if (!student) {
    redirect(`/login?next=${encodeURIComponent("/complete-profile")}`);
  }
  if (!student.emailVerified) {
    redirect(`/verify-email?email=${encodeURIComponent(student.email)}`);
  }
  if (student.profileComplete) {
    redirect(next);
  }

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto max-w-3xl px-5 py-12 lg:px-8 lg:py-20">
        <div className="rounded-[2rem] border border-[#dce4ef] bg-white p-6 shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-9">
          <div className="flex items-start gap-4">
            <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]">
              <ShieldCheck className="size-6" />
            </span>
            <div>
              <p className="eyebrow">Google registration</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-[-.04em]">
                Complete your Amaris student profile.
              </h1>
              <p className="mt-3 text-sm leading-6 text-[#60708a]">
                Google verified your email. Add the remaining student details before opening your private dashboard.
              </p>
            </div>
          </div>

          {params.error && (
            <Alert variant="destructive" className="mt-6">
              <AlertDescription>{params.error}</AlertDescription>
            </Alert>
          )}

          <form action={completeGoogleProfileAction} className="mt-7 grid gap-5">
            <input type="hidden" name="next" value={next} />
            <div className="grid gap-5 sm:grid-cols-2">
              <AuthField
                label="First name"
                name="firstName"
                autoComplete="given-name"
                defaultValue={student.firstName}
              />
              <AuthField
                label="Last name"
                name="lastName"
                autoComplete="family-name"
                defaultValue={student.lastName}
              />
            </div>
            <div className="grid gap-5 sm:grid-cols-2">
              <AuthField
                label="Mobile number"
                name="mobile"
                type="tel"
                autoComplete="tel"
                placeholder="071 234 5678"
              />
              <label className="grid gap-2 text-sm font-semibold text-[#263852]">
                Province
                <NativeSelect name="province" required className="h-12 w-full bg-white">
                  <NativeSelectOption value="">Select province</NativeSelectOption>
                  {provinces.map((province) => (
                    <NativeSelectOption key={province} value={province}>
                      {province}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </label>
            </div>
            <div className="grid gap-5 sm:grid-cols-2">
              <AuthField
                label="School, college or university"
                name="institution"
                autoComplete="organization"
              />
              <label className="grid gap-2 text-sm font-semibold text-[#263852]">
                Grade or academic level
                <NativeSelect name="academicLevel" required className="h-12 w-full bg-white">
                  <NativeSelectOption value="">Select level</NativeSelectOption>
                  {levels.map((level) => (
                    <NativeSelectOption key={level} value={level}>
                      {level}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </label>
            </div>
            <label className="flex items-start gap-3 rounded-xl bg-[#f5f7fb] p-4 text-sm leading-6 text-[#52617a]">
              <input name="terms" type="checkbox" required className="mt-1 size-4 accent-[#1f5bbd]" />
              <span>
                I accept the{" "}
                <Link href="/terms" className="font-semibold text-[#1f5bbd] underline">
                  Terms
                </Link>{" "}
                and{" "}
                <Link href="/privacy" className="font-semibold text-[#1f5bbd] underline">
                  Privacy Policy
                </Link>
                .
              </span>
            </label>
            <button
              type="submit"
              className="min-h-12 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white transition hover:bg-[#123d79]"
            >
              Save profile and continue
            </button>
          </form>
        </div>
      </section>
      <Footer />
    </main>
  );
}

function AuthField({
  label,
  name,
  type = "text",
  ...props
}: {
  label: string;
  name: string;
  type?: string;
} & Omit<React.ComponentProps<typeof Input>, "name" | "type">) {
  return (
    <label className="grid gap-2 text-sm font-semibold text-[#263852]">
      {label}
      <Input name={name} type={type} required className="h-12 bg-white" {...props} />
    </label>
  );
}
