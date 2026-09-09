import type { Metadata } from "next";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { academyBrand } from "@/lib/brand";

export const metadata: Metadata = { title: "Privacy Policy" };

const sections = [
  ["Information we collect", "We collect the registration details you provide, account security and verification information, enquiries, course enrolments, payment status and learning progress."],
  ["How we use it", "We use this information to create and secure your account, provide courses, verify payments, track progress, respond to support requests and improve the learning service."],
  ["Service providers", "Supabase provides authentication and profile storage. Payment and video providers process the information needed to deliver their services under their own privacy terms."],
  ["Security and retention", "Access is restricted by authenticated user identity and row-level database policies. We retain information only for legitimate learning, support, legal and accounting purposes."],
  ["Your choices", "You may ask to access, correct or delete eligible personal information, or raise a privacy concern, by contacting the academy."],
];

export default function PrivacyPage() {
  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><article className="mx-auto max-w-4xl px-5 py-16 lg:px-8 lg:py-24"><p className="eyebrow">Privacy policy</p><h1 className="section-title mt-4">Your student information stays protected.</h1><p className="mt-5 text-sm text-[#6a7890]">Effective 8 September 2026</p><div className="mt-10 grid gap-5">{sections.map(([title, body]) => <section key={title} className="rounded-2xl border border-[#dce4ef] bg-white p-6"><h2 className="text-xl font-semibold">{title}</h2><p className="mt-3 leading-7 text-[#5b6a82]">{body}</p></section>)}</div><p className="mt-8 text-sm leading-7 text-[#60708a]">Privacy enquiries: <a href={academyBrand.emailHref} className="font-semibold text-[#1f5bbd]">{academyBrand.email}</a> or <a href={academyBrand.phoneHref} className="font-semibold text-[#1f5bbd]">{academyBrand.phoneDisplay}</a>.</p></article><Footer /></main>;
}
