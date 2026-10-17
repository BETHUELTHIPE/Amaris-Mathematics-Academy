import type { Metadata } from "next";
import { ArrowUpRight, LockKeyhole, ShieldCheck } from "lucide-react";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";

const DJANGO_ADMIN_URL = "https://amaris-production-web.onrender.com/admin/";

export const metadata: Metadata = {
  title: "Amaris Admin",
  description: "Secure administration access for authorized Amaris Mathematics Academy staff.",
  robots: { index: false, follow: false },
};

export default function AmarisAdminPage() {
  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto max-w-4xl px-5 py-16 lg:px-8 lg:py-24">
        <div className="rounded-[2rem] border border-[#dce4ef] bg-white p-8 shadow-[0_22px_70px_rgba(9,35,75,.08)] sm:p-12">
          <div className="grid size-14 place-items-center rounded-2xl bg-[#eaf1fb] text-[#1f5bbd]">
            <LockKeyhole aria-hidden="true" className="size-7" />
          </div>
          <p className="mt-8 text-xs font-bold uppercase tracking-[.18em] text-[#1f5bbd]">
            Staff access
          </p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-.04em] text-[#0a1b36] sm:text-5xl">
            Amaris Admin
          </h1>
          <p className="mt-5 max-w-2xl text-lg leading-8 text-[#60708a]">
            Manage academy content and operations through the existing Django
            administration dashboard. This area is for authorized Amaris staff
            only.
          </p>
          <div className="mt-8 flex items-start gap-3 rounded-2xl bg-[#f5f7fb] p-5 text-sm leading-7 text-[#41546e]">
            <ShieldCheck aria-hidden="true" className="mt-1 size-5 shrink-0 text-[#1f5bbd]" />
            <p>
              Sign in using your approved Django staff account. Student accounts
              do not automatically provide administration access.
            </p>
          </div>
          <a
            href={DJANGO_ADMIN_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-9 inline-flex min-h-12 items-center justify-center gap-3 rounded-full bg-[#0b2a5b] px-7 py-3 font-semibold text-white transition hover:bg-[#173f7d] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#1f5bbd]"
            aria-label="Open Django administration (opens in a new tab)"
          >
            Open Django Admin
            <ArrowUpRight aria-hidden="true" className="size-5" />
          </a>
        </div>
      </section>
      <Footer />
    </main>
  );
}
