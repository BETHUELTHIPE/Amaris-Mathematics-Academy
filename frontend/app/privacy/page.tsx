import type { Metadata } from "next";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { getManagedBrand } from "@/lib/cms";

export const metadata: Metadata = { title: "Privacy Policy" };

const sections = [
  ["Tutor recruitment", "Tutor applicants provide contact details, teaching experience, availability and qualification copies. These are used for human recruitment review and application communication. Qualifications are private to the applicant and authorised recruitment administrators. Contact the academy to request access, correction, withdrawal or deletion."],
  ["Anonymous browser performance", "When enabled, we sample about 20% of eligible browsing sessions to understand browser loading, interaction responsiveness and layout stability (LCP, INP and CLS). The sitewide reports are reduced to daily histogram counts by broad page category, device class, coarse network category and performance range; we do not transmit names, account IDs, full URLs, cookies, interaction targets or query strings. Existing dashboard-only timing diagnostics may appear briefly in Render application logs. Browser Do Not Track and Global Privacy Control preferences are respected, and sitewide daily aggregates older than 90 days are removed."],
  ["Information we collect", "We collect the registration details you provide, account security and verification information, enquiries, course enrolments, payment status and learning progress."],
  ["How we use it", "We use this information to create and secure your account, provide courses, verify payments, track progress, respond to support requests and improve the learning service."],
  ["Service providers", "Supabase provides authentication and profile storage. Payment and video providers process the information needed to deliver their services under their own privacy terms."],
  ["Security and retention", "Access is restricted by authenticated user identity and row-level database policies. We retain information only for legitimate learning, support, legal and accounting purposes."],
  ["Your choices", "You may ask to access, correct or delete eligible personal information, or raise a privacy concern, by contacting the academy."],
];

export default async function PrivacyPage() {
  const academyBrand = await getManagedBrand();
  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><article className="mx-auto max-w-4xl px-5 py-16 lg:px-8 lg:py-24"><p className="eyebrow">Privacy policy</p><h1 className="section-title mt-4">Your personal information stays protected.</h1><p className="mt-5 text-sm text-[#4c5d73]">Effective 8 September 2026</p><div className="mt-10 grid gap-5">{sections.map(([title, body]) => <section key={title} className="rounded-2xl border border-[#dce4ef] bg-white p-6"><h2 className="text-xl font-semibold">{title}</h2><p className="mt-3 leading-7 text-[#5b6a82]">{body}</p></section>)}</div><p className="mt-8 text-sm leading-7 text-[#60708a]">Privacy enquiries: <a href={academyBrand.emailHref} className="font-semibold text-[#1f5bbd]">{academyBrand.email}</a> or <a href={academyBrand.phoneHref} className="font-semibold text-[#1f5bbd]">{academyBrand.phoneDisplay}</a>.</p></article><Footer /></main>;
}
