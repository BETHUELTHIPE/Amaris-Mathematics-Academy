import type { Metadata } from "next";
import { ArrowRight, BadgeCheck, BookOpen, BriefcaseBusiness, Clock3, GraduationCap, Laptop, Moon, ShieldCheck, Sun, Users } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";

export const metadata: Metadata = {
  title: "Matric Upgrades & Rewrite Classes for Working Adults",
  description: "Upgrade or rewrite matric subjects with flexible online tuition from Amaris Mathematics Academy. Study around day shifts, night shifts and family commitments across South Africa.",
};

const steps = [
  { number: "01", title: "Register for your matric examination", description: "Confirm which NSC or Senior Certificate route applies to you and register with the Department of Basic Education or an approved examination centre before the official deadline." },
  { number: "02", title: "Attend online classes at Amaris", description: "Get structured live tutoring, revision, exam practice and guidance from Amaris tutors wherever you live in South Africa." },
  { number: "03", title: "We work around day and night shifts", description: "Work during the day? Look for evening sessions. Work at night? Look for daytime sessions. Select an available tutor slot that suits your timetable." },
  { number: "04", title: "Get help across matric subjects", description: "Ask us about support for Mathematics, Mathematical Literacy, Physical Sciences, Life Sciences, Accounting, languages and other school subjects. Subject availability is confirmed when booking." },
];

const audiences = [
  { title: "Day-shift workers", detail: "Learn after work, on a day off or during available weekend sessions.", icon: Sun },
  { title: "Night-shift workers", detail: "Choose available daytime lessons when your shifts finish.", icon: Moon },
  { title: "Parents and caregivers", detail: "Balance learning with family responsibilities and your own pace.", icon: Users },
  { title: "Adults returning to education", detail: "Build confidence, revisit key concepts and prepare for your next exam.", icon: BriefcaseBusiness },
];

export default function MatricUpgradesPage() {
  return (
    <main className="min-h-screen bg-[#f5f7fb] text-[#0a1b36]">
      <Header />
      <section className="relative overflow-hidden bg-[#07152d] text-white">
        <div className="pointer-events-none absolute -right-32 top-0 size-[32rem] rounded-full bg-[#214e9c]/25 blur-3xl" aria-hidden="true" />
        <div className="relative mx-auto grid max-w-7xl gap-12 px-5 py-20 lg:grid-cols-[1.2fr_.8fr] lg:items-center lg:px-8 lg:py-28">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-[#ffcc66]/40 bg-[#ffcc66]/10 px-4 py-2 text-xs font-semibold tracking-widest text-[#ffcc66] uppercase"><GraduationCap aria-hidden="true" className="size-4" /> Matric upgrades · Matric rewrites · Adult learners</div>
            <h1 className="mt-7 max-w-4xl text-4xl leading-[1.1] font-extrabold tracking-tight sm:text-5xl lg:text-6xl">Your work schedule should not end <span className="text-[#ffcc66]">your education.</span></h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-white/80">Passed matric but need higher marks? Did not finish Grade 12? Working day shifts or night shifts? Amaris is here to help you prepare for a second chance — with online lessons designed around real South African lives.</p>
            <div className="mt-9 flex flex-wrap gap-3">
              <a href="/register" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-[#ffcc66] px-6 py-3 font-bold text-[#07152d] transition hover:bg-[#ffe09a]">Start learning with Amaris <ArrowRight aria-hidden="true" className="size-4" /></a>
              <a href="/book-online-live-class" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-white/40 px-6 py-3 font-semibold text-white transition hover:bg-white/10">Book an online lesson</a>
            </div>
            <p className="mt-5 flex items-center gap-2 text-sm text-white/65"><ShieldCheck aria-hidden="true" className="size-4 text-[#ffcc66]" /> Online tutoring across South Africa · Exams registered separately</p>
          </div>
          <div className="relative rounded-3xl border border-white/20 bg-white/10 p-7 shadow-2xl backdrop-blur-sm">
            <p className="text-xs font-bold tracking-[.2em] text-[#ffcc66] uppercase">Your future is still possible</p>
            <h2 className="mt-3 text-3xl font-bold">You can work. You can study. You can grow.</h2>
            <div className="mt-7 grid gap-4">
              <div className="flex items-start gap-4 rounded-2xl bg-white/10 p-4"><Clock3 aria-hidden="true" className="mt-1 size-6 shrink-0 text-[#ffcc66]" /><div><p className="font-bold">Flexible class bookings</p><p className="mt-1 text-sm text-white/70">Look for available classes that fit your day or night work schedule.</p></div></div>
              <div className="flex items-start gap-4 rounded-2xl bg-white/10 p-4"><Laptop aria-hidden="true" className="mt-1 size-6 shrink-0 text-[#ffcc66]" /><div><p className="font-bold">Learn from anywhere</p><p className="mt-1 text-sm text-white/70">Attend online from home or another suitable location with internet access.</p></div></div>
              <div className="flex items-start gap-4 rounded-2xl bg-white/10 p-4"><BookOpen aria-hidden="true" className="mt-1 size-6 shrink-0 text-[#ffcc66]" /><div><p className="font-bold">Prepare for your next chapter</p><p className="mt-1 text-sm text-white/70">Work towards stronger matric results and potential college or university opportunities.</p></div></div>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-20 lg:px-8" aria-labelledby="steps-title">
        <div className="max-w-3xl"><p className="text-sm font-bold tracking-widest text-[#2457a5] uppercase">Four steps to move forward</p><h2 id="steps-title" className="mt-3 text-3xl font-extrabold tracking-tight sm:text-4xl">Your matric upgrade journey</h2><p className="mt-4 text-lg text-[#53647d]">Your dream deserves a practical plan. Start with exam registration, then prepare with tutoring that works for you.</p></div>
        <div className="mt-10 grid gap-5 md:grid-cols-2">{steps.map((step) => <article key={step.number} className="rounded-3xl border border-[#dae4f0] bg-white p-7 shadow-sm"><span className="text-3xl font-black text-[#1f5ab5]">{step.number}</span><h3 className="mt-5 text-xl font-bold">{step.title}</h3><p className="mt-3 leading-7 text-[#53647d]">{step.description}</p></article>)}</div>
      </section>

      <section className="bg-white py-20"><div className="mx-auto max-w-7xl px-5 lg:px-8"><div className="max-w-3xl"><p className="text-sm font-bold tracking-widest text-[#2457a5] uppercase">Built for your life</p><h2 className="mt-3 text-3xl font-extrabold sm:text-4xl">Education for people who cannot stop working</h2><p className="mt-4 text-lg text-[#53647d]">You should not have to choose between earning an income, supporting your family and improving your education.</p></div><div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{audiences.map(({title,detail,icon:Icon})=><article key={title} className="rounded-2xl border border-[#dae4f0] bg-[#f7faff] p-6"><Icon aria-hidden="true" className="size-9 text-[#1f5ab5]" /><h3 className="mt-5 text-lg font-bold">{title}</h3><p className="mt-3 text-sm leading-6 text-[#53647d]">{detail}</p></article>)}</div></div></section>

      <section className="mx-auto grid max-w-7xl gap-10 px-5 py-20 lg:grid-cols-2 lg:items-center lg:px-8"><div><p className="text-sm font-bold tracking-widest text-[#2457a5] uppercase">More than a pass mark</p><h2 className="mt-3 text-3xl font-extrabold sm:text-4xl">Build a route towards college or university.</h2><p className="mt-5 leading-8 text-[#53647d]">Whether you want to qualify for a diploma, degree or vocational programme, improved matric results may help you meet the entrance requirements. We help you focus on the subjects and marks relevant to your goal.</p><p className="mt-4 leading-7 text-[#53647d]">Admission is determined by each institution and programme. Matric upgrades do not automatically guarantee acceptance, but preparation can open possibilities.</p></div><div className="rounded-3xl bg-[#edf3ff] p-8"><h3 className="text-xl font-bold">How we support your goal</h3><ul className="mt-6 space-y-5">{["Subject-specific tutoring and revision","Online lessons with a tutor","Past-paper practice and exam preparation","Study support built around available class times","A welcoming route back into learning"].map(x=><li key={x} className="flex gap-3"><BadgeCheck aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-[#2563b5]" /><span>{x}</span></li>)}</ul></div></section>

      <section className="bg-[#07152d] py-18 text-white"><div className="mx-auto max-w-7xl px-5 py-16 text-center lg:px-8"><p className="text-sm font-bold tracking-widest text-[#ffcc66] uppercase">South Africa, your next chapter starts here</p><h2 className="mx-auto mt-4 max-w-4xl text-3xl font-extrabold sm:text-5xl">You are not too late to improve your matric results.</h2><p className="mx-auto mt-5 max-w-2xl text-lg leading-8 text-white/75">Whatever your age, work shift or previous results, enquire about a learning option that fits your circumstances and eligibility.</p><div className="mt-9 flex flex-wrap justify-center gap-4"><a className="inline-flex min-h-12 items-center gap-2 rounded-xl bg-[#ffcc66] px-7 py-3 font-bold text-[#07152d]" href="/register">Register with Amaris <ArrowRight aria-hidden="true" className="size-4" /></a><a className="inline-flex min-h-12 items-center rounded-xl border border-white/40 px-7 py-3 font-semibold" href="/contact">Ask about matric upgrade subjects</a></div></div></section>

      <section className="mx-auto max-w-7xl px-5 py-10 text-sm leading-7 text-[#53647d] lg:px-8"><h2 className="font-bold text-[#0a1b36]">Important: examination registration</h2><p>Amaris provides tutoring and academic preparation, not official matric examination registration or certification. Candidates must register through the Department of Basic Education, their provincial education office or an authorised examination centre, depending on their qualification route. Check the current dates and eligibility before applying. <a className="font-semibold text-[#1e56a8] underline" href="https://www.education.gov.za/Curriculum/SeniorCertificate/SCRegistration.aspx" target="_blank" rel="noopener noreferrer">Official Senior Certificate registration guidance</a> · <a className="font-semibold text-[#1e56a8] underline" href="https://www.gov.za/services/services-residents/education-and-training/basic-education/register-rewrite-matric-subjects" target="_blank" rel="noopener noreferrer">Official matric rewrite information</a>.</p></section>
      <Footer />
    </main>
  );
}
