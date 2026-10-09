import type { Metadata } from "next";
import Link from "next/link";
import { LockKeyhole, ShieldCheck } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { StudentDashboardNavigation } from "@/components/dashboard/student-navigation";
import { requireVerifiedStudent } from "@/lib/auth";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Profile & Security", robots: { index: false, follow: false } };

export default async function StudentProfilePage() {
  const student = await requireVerifiedStudent("/dashboard/profile");
  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto grid max-w-7xl gap-7 px-5 py-12 lg:grid-cols-[240px_1fr] lg:px-8">
        <StudentDashboardNavigation currentPath="/dashboard/profile" />
        <div className="min-w-0">
          <p className="eyebrow">Student dashboard</p>
          <h1 className="mt-3 text-4xl font-semibold">Profile & security</h1>
          <p className="mt-3 text-[#60708a]">Your verified sign-in identity. Account details are shown only to you.</p>
          <section className="mt-7 rounded-2xl border border-[#dce4ef] bg-white p-7">
            <h2 className="text-xl font-semibold">Account information</h2>
            <dl className="mt-5 grid gap-5">
              <div><dt className="text-sm font-semibold text-[#60708a]">Student name</dt><dd className="mt-1 break-words font-semibold">{student.displayName}</dd></div>
              <div><dt className="text-sm font-semibold text-[#60708a]">Email address</dt><dd className="mt-1 break-all font-semibold">{student.email}</dd></div>
              <div className="flex items-center gap-2"><ShieldCheck className="size-5 text-[#13715f]" aria-hidden="true" /><span className="font-semibold">Email verified</span></div>
            </dl>
          </section>
          <section className="mt-6 rounded-2xl border border-[#dce4ef] bg-white p-7">
            <h2 className="flex items-center gap-2 text-xl font-semibold"><LockKeyhole className="size-5" aria-hidden="true" />Account security</h2>
            <p className="mt-3 text-sm leading-7 text-[#60708a]">For security, password changes start with a fresh reset link sent to your registered email address.</p>
            <Link href="/forgot-password" className="mt-5 inline-flex min-h-11 items-center rounded-full bg-[#0b2a5b] px-6 font-bold text-white">Request a password reset link</Link>
          </section>
        </div>
      </section>
      <Footer />
    </main>
  );
}
