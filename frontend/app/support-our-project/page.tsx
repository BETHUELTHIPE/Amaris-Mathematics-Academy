import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  GraduationCap,
  HandHeart,
  HeartHandshake,
  Laptop,
  Mail,
  ShieldCheck,
  Users,
} from "lucide-react";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { ShareSupportProject, PUBLIC_SUPPORT_URL } from "@/components/site/share-support-project";
import { getManagedBrand } from "@/lib/cms";

export const metadata: Metadata = {
  title: "Support Our Project",
  description:
    "Help Amaris Mathematics Academy widen access to clear, flexible mathematics learning. Explore learner sponsorships, education partnerships and ways to contribute.",
  alternates: { canonical: PUBLIC_SUPPORT_URL },
  openGraph: {
    title: "Support Our Project | Amaris Mathematics Academy",
    description: "Share our education project with sponsors, mentors and partners helping South African learners.",
    url: PUBLIC_SUPPORT_URL,
    type: "website",
  },
};

const waysToHelp = [
  {
    icon: GraduationCap,
    title: "Support a learner",
    description:
      "Ask us about helping a learner access structured Mathematics lessons or learning materials. We will discuss the learner's needs and a suitable arrangement before any commitment.",
  },
  {
    icon: BookOpen,
    title: "Contribute learning resources",
    description:
      "Support the development of revision guides, practice activities and accessible educational content for school, TVET and university learners.",
  },
  {
    icon: Laptop,
    title: "Become a technology partner",
    description:
      "Collaborate on accessible online learning, reliable digital services and tools that help students learn wherever they are.",
  },
  {
    icon: Users,
    title: "Share your expertise",
    description:
      "Educators, mentors, employers and community organisations can contact us about tutoring partnerships, career guidance or learner support.",
  },
];

export default async function SupportOurProjectPage() {
  const academyBrand = await getManagedBrand();

  return (
    <main className="min-h-screen bg-[#f5f7fb] text-[#07152d]">
      <Header />
      <section className="relative overflow-hidden bg-[#07152d] px-5 py-20 text-white sm:py-24 lg:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute -right-24 top-0 size-80 rounded-full bg-[#1f5bbd]/25 blur-3xl" />
        <div className="relative mx-auto max-w-7xl">
          <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[.16em] text-[#ffcc66]">
            <HandHeart className="size-5" aria-hidden="true" /> Support Our Project
          </p>
          <h1 className="mt-5 max-w-4xl text-4xl font-semibold leading-tight tracking-[-.04em] sm:text-6xl">
            Help more learners keep moving forward.
          </h1>
          <p className="mt-6 max-w-3xl text-lg leading-8 text-white/75">
            Amaris Mathematics Academy is building flexible Mathematics learning for South Africans at school, in TVET programmes and at university. Your partnership can help us reach learners who need clear explanations and opportunities to continue their education.
          </p>
          <div className="mt-9 flex flex-wrap gap-4">
            <Link
              href="/contact"
              className="inline-flex min-h-12 items-center gap-2 rounded-full bg-[#ffcc66] px-6 py-3 font-semibold text-[#07152d] transition hover:bg-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"
            >
              Discuss how to help <ArrowRight className="size-5" aria-hidden="true" />
            </Link>
            <Link
              href="/about"
              className="inline-flex min-h-12 items-center rounded-full border border-white/40 px-6 py-3 font-semibold text-white transition hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"
            >
              Learn about Amaris
            </Link>
          </div>
        </div>
      </section>

      <section className="bg-[#eaf1fb] px-5 py-12 lg:px-8" aria-labelledby="share-our-project">
        <div className="mx-auto max-w-7xl">
          <p className="text-xs font-bold uppercase tracking-[.18em] text-[#1f5bbd]">Help spread the word</p>
          <h2 id="share-our-project" className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl">
            Share this project with someone who could help.
          </h2>
          <p className="mt-3 max-w-3xl text-base leading-7 text-[#526781]">
            A shared link can connect Amaris with a potential sponsor, employer, education partner or mentor.
            You can copy the public page link, use your device&apos;s share menu, or send it on WhatsApp.
          </p>
          <ShareSupportProject />
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-16 lg:px-8 lg:py-20" aria-labelledby="support-options">
        <div className="max-w-3xl">
          <p className="text-xs font-bold uppercase tracking-[.18em] text-[#1f5bbd]">Ways to make a difference</p>
          <h2 id="support-options" className="mt-3 text-3xl font-semibold tracking-[-.04em] sm:text-4xl">
            Choose the kind of support that suits you.
          </h2>
          <p className="mt-5 text-base leading-8 text-[#526781]">
            Individuals, businesses, educators and community organisations are welcome to get in touch. These are opportunities to discuss, not pre-approved sponsorship packages.
          </p>
        </div>
        <div className="mt-9 grid gap-5 md:grid-cols-2">
          {waysToHelp.map(({ icon: Icon, title, description }) => (
            <article key={title} className="rounded-3xl border border-[#dce4ef] bg-white p-7 shadow-sm sm:p-8">
              <span className="grid size-14 place-items-center rounded-2xl bg-[#eaf1fb] text-[#1f5bbd]">
                <Icon className="size-7" aria-hidden="true" />
              </span>
              <h3 className="mt-6 text-2xl font-semibold tracking-tight">{title}</h3>
              <p className="mt-3 text-base leading-7 text-[#526781]">{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="bg-white px-5 py-16 lg:px-8 lg:py-20" aria-labelledby="support-process">
        <div className="mx-auto max-w-7xl">
          <div className="grid gap-12 lg:grid-cols-[.9fr_1.1fr] lg:items-start">
            <div>
              <HeartHandshake className="size-10 text-[#1f5bbd]" aria-hidden="true" />
              <h2 id="support-process" className="mt-5 text-3xl font-semibold tracking-[-.04em] sm:text-4xl">
                A clear process, without pressure.
              </h2>
              <p className="mt-5 max-w-xl text-base leading-8 text-[#526781]">
                We want potential supporters to understand the purpose, expected use and practical arrangements before deciding whether to contribute.
              </p>
            </div>
            <ol className="grid gap-4">
              {[
                ["01", "Start a conversation", "Tell us whether you want to sponsor learning, supply resources or explore a partnership."],
                ["02", "Agree on the details", "We discuss the relevant learner needs, the proposed support and how progress could be shared."],
                ["03", "Confirm an arrangement", "Any contribution or partnership should be agreed through an appropriate, documented process."],
              ].map(([number, title, description]) => (
                <li key={number} className="flex gap-5 rounded-2xl border border-[#dce4ef] bg-[#f5f7fb] p-6">
                  <span className="shrink-0 font-mono text-sm font-bold text-[#1f5bbd]">{number}</span>
                  <div>
                    <h3 className="text-lg font-semibold">{title}</h3>
                    <p className="mt-2 text-sm leading-7 text-[#526781]">{description}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
          <div className="mt-8 flex items-start gap-3 rounded-2xl border border-[#dce4ef] bg-[#f5f7fb] p-5">
            <ShieldCheck className="mt-0.5 size-6 shrink-0 text-[#1f5bbd]" aria-hidden="true" />
            <p className="text-sm leading-7 text-[#526781]">
              <strong className="text-[#07152d]">Payment safety:</strong> This page does not collect donations or card details. Do not send banking information, passwords or payment details in an enquiry. Any future payment method will be confirmed through an official Amaris channel.
            </p>
          </div>
        </div>
      </section>

      <section className="px-5 py-16 lg:px-8 lg:py-20">
        <div className="mx-auto flex max-w-7xl flex-col justify-between gap-8 rounded-[2rem] bg-[#0b2a5b] p-8 text-white md:flex-row md:items-center sm:p-12">
          <div className="max-w-2xl">
            <p className="text-sm font-semibold uppercase tracking-[.16em] text-[#ffcc66]">Get involved</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Let&apos;s talk about what we can build together.</h2>
            <p className="mt-4 text-base leading-8 text-white/70">
              Send our team a short message about how you would like to support the Amaris education project.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-3">
            <Link
              href="/contact"
              className="inline-flex min-h-12 items-center gap-2 rounded-full bg-[#ffcc66] px-6 py-3 font-semibold text-[#07152d] transition hover:bg-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"
            >
              Contact the team <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
            <a
              href={academyBrand.emailHref}
              className="inline-flex min-h-12 items-center gap-2 rounded-full border border-white/45 px-6 py-3 font-semibold text-white transition hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"
            >
              <Mail className="size-4" aria-hidden="true" /> Email us
            </a>
          </div>
        </div>
      </section>
      <Footer />
    </main>
  );
}
