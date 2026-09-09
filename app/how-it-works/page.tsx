import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpenCheck, CircleDollarSign, ClipboardCheck, UserRoundCheck } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";

export const metadata: Metadata = { title: "How It Works" };

const steps = [
  [UserRoundCheck, "01", "Create your student profile", "Register before buying so your courses, payments and progress stay safely connected to you."],
  [ClipboardCheck, "02", "Choose the right pathway", "Filter by curriculum and level, then review the outcomes and complete course structure."],
  [CircleDollarSign, "03", "Complete secure payment", "Pay through PayFast. Google Pay appears inside checkout when it is available for your device."],
  [BookOpenCheck, "04", "Learn, practise and progress", "Open your private dashboard, continue from your last lesson and measure each completed step."],
] as const;

export default function HowItWorksPage() { return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="bg-[#07152d] text-white"><div className="mx-auto max-w-7xl px-5 py-20 lg:px-8"><p className="text-xs font-bold uppercase tracking-[.18em] text-[#ffcc66]">How it works</p><h1 className="mt-5 max-w-4xl text-5xl font-semibold leading-[1.04] tracking-[-.05em] sm:text-7xl">One secure path from choosing to achieving.</h1><p className="mt-6 max-w-2xl text-lg leading-8 text-white/65">No confusing menus and no open course links. Your account brings learning, payment history and progress together.</p></div></section><section className="mx-auto max-w-5xl px-5 py-20 lg:px-8"><div className="grid gap-5">{steps.map(([Icon,number,title,copy]) => <article key={number} className="grid gap-5 rounded-3xl border border-[#dce4ef] bg-white p-6 shadow-[0_18px_55px_rgba(7,21,45,.05)] sm:grid-cols-[70px_1fr] sm:p-8"><div className="grid size-14 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]"><Icon className="size-6" /></div><div><p className="font-mono text-xs font-bold text-[#1f5bbd]">STEP {number}</p><h2 className="mt-2 text-2xl font-semibold">{title}</h2><p className="mt-3 max-w-2xl text-base leading-7 text-[#60708a]">{copy}</p></div></article>)}</div><div className="mt-10 text-center"><Link href="/register" className="inline-flex items-center gap-2 rounded-full bg-[#0b2a5b] px-7 py-4 font-bold text-white">Create your profile <ArrowRight className="size-4" /></Link></div></section><Footer /></main>; }
