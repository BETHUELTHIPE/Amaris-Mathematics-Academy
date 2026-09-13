import type { Metadata } from "next";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { getManagedBrand } from "@/lib/cms";

export const metadata: Metadata = { title: "Student Terms" };

const sections = [
  ["Student accounts", "You must provide accurate registration information, keep your password private and use only your own student account. Email verification is required before paid course access."],
  ["Courses and access", "Course access is personal and may not be shared, copied or redistributed. Access begins only after the applicable payment has been verified."],
  ["Learning materials", "Videos, notes, worked examples and assessments remain the intellectual property of Amaris Mathematics Academy or its licensors."],
  ["Payments and support", "Course prices are shown in South African rand. Payment, refund and access questions should be sent to the academy using the contact details below."],
  ["Responsible use", "You may not attempt to bypass authentication, access another student's information or interfere with the website or its learning services."],
];

export default async function TermsPage() {
  const academyBrand = await getManagedBrand();
  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><article className="mx-auto max-w-4xl px-5 py-16 lg:px-8 lg:py-24"><p className="eyebrow">Student terms</p><h1 className="section-title mt-4">Clear rules for a safe learning space.</h1><p className="mt-5 text-sm text-[#69778f]">Effective 8 September 2026</p><div className="mt-10 grid gap-5">{sections.map(([title, body]) => <section key={title} className="rounded-2xl border border-[#dce4ef] bg-white p-6"><h2 className="text-xl font-semibold">{title}</h2><p className="mt-3 leading-7 text-[#5b6a82]">{body}</p></section>)}</div><p className="mt-8 text-sm leading-7 text-[#60708a]">Questions about these terms: <a href={academyBrand.emailHref} className="font-semibold text-[#1f5bbd]">{academyBrand.email}</a> or <a href={academyBrand.phoneHref} className="font-semibold text-[#1f5bbd]">{academyBrand.phoneDisplay}</a>.</p></article><Footer /></main>;
}
