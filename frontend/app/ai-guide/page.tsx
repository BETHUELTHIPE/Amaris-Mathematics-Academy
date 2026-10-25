import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Bot, GraduationCap, Headphones, MessageCircle } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { AmarisAssistantLauncher } from "@/components/site/amaris-assistant-launcher";
import { AiGuideTour } from "@/components/site/ai-guide-tour";

export const metadata: Metadata = {
  title: "Amaris AI Guide — Simple English",
  description: "Listen to a simple explanation of Amaris Mathematics Academy. Learn how to register, book online tutoring and use the student website.",
};

export default function AiGuidePage() {
  return (
    <main className="min-h-screen bg-[#f5f7fb] text-[#07152d]">
      <Header />
      <section className="bg-[#07152d] px-5 py-16 text-white lg:px-8">
        <div className="mx-auto max-w-6xl">
          <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-widest text-[#ffcc66]"><Bot className="size-5" aria-hidden="true" /> Amaris AI Guide</p>
          <h1 className="mt-5 max-w-4xl text-4xl font-semibold leading-tight tracking-tight sm:text-6xl">We explain Amaris in simple English.</h1>
          <p className="mt-6 max-w-3xl text-lg leading-8 text-white/75">Are you a learner, a parent or someone who works and wants to study? Start here. We will explain how our website works, one simple step at a time.</p>
          <div className="mt-7 flex flex-wrap gap-3 text-sm text-white/75">
            <span className="inline-flex items-center gap-2"><Headphones className="size-4 text-[#ffcc66]" aria-hidden="true" /> Listen to the guide</span>
            <span className="inline-flex items-center gap-2"><MessageCircle className="size-4 text-[#ffcc66]" aria-hidden="true" /> Chat or talk to our assistant</span>
            <span className="inline-flex items-center gap-2"><GraduationCap className="size-4 text-[#ffcc66]" aria-hidden="true" /> Learn how to join</span>
          </div>
        </div>
      </section>
      <section className="mx-auto max-w-6xl px-5 py-12 lg:px-8">
        <AiGuideTour />
        <div className="mt-8 grid gap-5 md:grid-cols-2">
          <article className="rounded-3xl border border-[#dce4ef] bg-white p-7">
            <h2 className="text-2xl font-semibold">Want to ask a question?</h2>
            <p className="mt-3 text-sm leading-7 text-[#526781]">Choose the <strong>Amaris Assistant</strong> button in the bottom corner. Select Chat to type, or Voice to speak and hear a reply where your browser supports it. Live AI answers depend on the assistant service being available.</p>
            <p className="mt-3 text-xs leading-6 text-[#60708a]">Please do not share passwords, payment card details or verification codes.</p>
          </article>
          <article className="rounded-3xl border border-[#dce4ef] bg-white p-7">
            <h2 className="text-2xl font-semibold">Ready to get started?</h2>
            <p className="mt-3 text-sm leading-7 text-[#526781]">You can register, explore courses or ask us about online lessons. If you need personal help, our team can assist you.</p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Link href="/register" className="inline-flex min-h-11 items-center gap-2 rounded-full bg-[#0b2a5b] px-5 py-2 font-semibold text-white">Register <ArrowRight className="size-4" aria-hidden="true" /></Link>
              <Link href="/book-online-live-class" className="inline-flex min-h-11 items-center rounded-full border border-[#c9d5e5] px-5 py-2 font-semibold text-[#0b2a5b]">Book a lesson</Link>
              <Link href="/contact" className="inline-flex min-h-11 items-center rounded-full border border-[#c9d5e5] px-5 py-2 font-semibold text-[#0b2a5b]">Contact us</Link>
            </div>
          </article>
        </div>
      </section>
      <AmarisAssistantLauncher />
      <Footer />
    </main>
  );
}
