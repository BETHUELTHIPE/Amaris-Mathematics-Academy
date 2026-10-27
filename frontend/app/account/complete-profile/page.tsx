import type { Metadata } from "next";
import Link from "next/link";
import { requireVerifiedStudent } from "@/lib/auth";
import { getVerifiedStudentBookingName } from "@/lib/registered-booking-name";
import { completeStudentBookingProfile } from "./actions";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Complete your verified student profile",
  robots: { index: false, follow: false },
};

export default async function CompleteProfilePage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const student = await requireVerifiedStudent("/account/complete-profile");
  const currentName = await getVerifiedStudentBookingName(student.id);
  const { error } = await searchParams;

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto max-w-xl px-5 py-16">
        <div className="rounded-3xl border border-[#dce4ef] bg-white p-7 shadow-sm sm:p-10">
          <p className="eyebrow">Private verified account</p>
          <h1 className="mt-4 text-3xl font-semibold text-[#07152d]">Complete your student profile</h1>
          <p className="mt-4 text-sm leading-7 text-[#526781]">
            Amaris needs your actual registered first and last name before reserving a tutor or
            starting PayFast checkout. This updates your own verified account only,
            never a payment form, tutor account, or another student record.
          </p>
          <p className="mt-4 rounded-xl bg-[#f1f5fb] p-4 text-sm text-[#263852]">
            Verified email: <strong>{student.email}</strong>
          </p>
          {error && <p role="alert" className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">{error}</p>}
          {currentName && <p className="mt-5 text-sm text-[#526781]">Current registered name: <strong>{currentName.fullName}</strong></p>}
          <form action={completeStudentBookingProfile} className="mt-7 grid gap-5">
            <label className="grid gap-2 text-sm font-semibold text-[#263852]">
              Actual first name
              <input name="firstName" type="text" autoComplete="given-name" minLength={2} maxLength={80} required
                defaultValue={currentName?.firstName || ""}
                className="min-h-12 rounded-xl border border-[#cbd6e5] px-4 font-normal" />
            </label>
            <label className="grid gap-2 text-sm font-semibold text-[#263852]">
              Actual last name
              <input name="lastName" type="text" autoComplete="family-name" minLength={2} maxLength={80} required
                defaultValue={currentName?.lastName || ""}
                className="min-h-12 rounded-xl border border-[#cbd6e5] px-4 font-normal" />
            </label>
            <p className="text-sm leading-6 text-[#526781]">
              Use the same name you registered with. Generic values such as Student Learner are not accepted.
              Your email verification and access permissions do not change.
            </p>
            <button type="submit" className="min-h-12 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white">
              Save registered name and return to booking
            </button>
          </form>
          <Link href="/book-online-live-class" className="mt-6 inline-block text-sm font-semibold text-[#1f5bbd]">
            Back to booking
          </Link>
        </div>
      </section>
      <Footer />
    </main>
  );
}
