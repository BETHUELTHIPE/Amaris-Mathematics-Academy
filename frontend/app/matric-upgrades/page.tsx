import type { Metadata } from "next";
import { ArrowDown, ArrowRight, BadgeCheck, BookOpen, BriefcaseBusiness, Check, Clock3, GraduationCap, Laptop, MapPin, Moon, ShieldCheck, Sun, Users } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";

export const metadata: Metadata = {
  title: "Matric Upgrades & Rewrite Tuition for Adults",
  description: "Your next chapter starts with a stronger matric. Explore online tuition for adults, shift workers and returning learners. Secure your exam centre before attending Amaris classes.",
};

const focus = "focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#1f5bbd]";
const darkFocus = "focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#ffcc66]";
const steps = [
  { number: "01", title: "Secure your exam centre", description: "Confirm your eligibility and qualification route, contact an authorised examination centre or provincial education office, and secure your centre before attending any Amaris class." },
  { number: "02", title: "Choose your subjects and goal", description: "Tell us which marks you want to improve and what you are working towards. We will confirm subject support, available tutors and lesson options with you." },
  { number: "03", title: "Find lessons that fit your life", description: "Look for available daytime, evening or weekend sessions around your work and family commitments. Class times depend on tutor availability." },
  { number: "04", title: "Practise with a purpose", description: "Use tutor guidance, revision and past-paper practice to prepare for the examination you will write through your secured exam centre." },
];
const audiences = [
  { title: "Working adults", detail: "Keep moving towards your education goals while you earn a living.", icon: BriefcaseBusiness },
  { title: "Day- and night-shift workers", detail: "Look for available lesson times that work around your shifts.", icon: Moon },
  { title: "Parents and caregivers", detail: "Build a study routine around your family responsibilities.", icon: Users },
  { title: "Anyone ready to improve", detail: "Improve a pass, rewrite a subject or return to learning after time away.", icon: Sun },
];
const faqs = [
  ["Can I attend classes before securing an exam centre?", "No. You must secure your examination centre before attending Amaris classes. You can enquire or create an Amaris account while planning, but neither action secures an exam centre or registers you for an examination."],
  ["Will Amaris register me for matric examinations?", "Amaris provides tutoring and academic preparation. You must arrange examination registration separately through the Department of Basic Education, your provincial education office or an authorised examination centre, as appropriate to your route."],
  ["Can I study while working shifts?", "Yes, you can enquire about online lessons around your work schedule. Daytime, evening and weekend options depend on the tutors and slots available. Confirm suitable times before booking."],
  ["Which subjects and fees are available?", "Tell us which subjects you want to upgrade. Our team can confirm subject support, tutor availability and the applicable fees. Do not assume that every subject or class time is currently available."],
  ["Will better marks guarantee university or college admission?", "Improved results may help you meet entrance requirements, but each institution and programme makes its own admission decisions. Check the requirements for your intended course before choosing the subjects you want to improve."],
];

export default function MatricUpgradesPage() {
  return (
    <main className="min-h-screen bg-[#f5f7fb] text-[#0a1b36]">
      <Header />
      <section className="relative overflow-hidden bg-[#07152d] text-white">
        <div className="graph-paper pointer-events-none absolute inset-0 opacity-20" aria-hidden="true" />
        <div className="relative mx-auto grid max-w-7xl gap-12 px-5 py-16 lg:grid-cols-[1.2fr_.8fr] lg:items-center lg:px-8 lg:py-24">
          <div>
            <p className="inline-flex items-start gap-2 text-xs font-bold uppercase leading-6 tracking-[.16em] text-[#ffcc66]"><GraduationCap aria-hidden="true" className="mt-1 size-4 shrink-0" />Matric upgrades · Adult learners · New possibilities</p>
            <h1 className="mt-6 max-w-4xl text-4xl font-semibold leading-[1.06] tracking-[-.045em] sm:text-6xl lg:text-7xl">Your next chapter starts with <span className="text-[#ffcc66]">a stronger matric.</span></h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-[#d0dcee]">Your previous results do not have to define your next step. Whether you are working, raising a family or returning to study, get focused online tuition to help you work towards better matric marks.</p>
            <p className="mt-4 max-w-xl text-base leading-7 text-[#d0dcee]">Improve a pass. Rewrite a subject. Rebuild your confidence. Make room for the future you are working towards.</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <a href="#exam-centre" className={`inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-[#ffcc66] px-6 py-3.5 font-bold text-[#07152d] hover:bg-[#ffe09a] ${darkFocus}`}>Start my matric upgrade <ArrowDown aria-hidden="true" className="size-4 shrink-0" /></a>
              <a href="/book-online-live-class" className={`inline-flex min-h-12 items-center justify-center rounded-full border border-white/40 px-6 py-3.5 font-semibold text-white hover:bg-white/10 ${darkFocus}`}>Centre secured? View classes</a>
            </div>
            <p className="mt-5 flex items-start gap-2 text-sm leading-6 text-[#d0dcee]"><ShieldCheck aria-hidden="true" className="mt-1 size-4 shrink-0 text-[#ffcc66]" />You must secure your exam centre before attending classes.</p>
          </div>
          <aside className="rounded-3xl border border-white/20 bg-white/5 p-7 sm:p-8" aria-labelledby="possibilities-heading">
            <p className="text-xs font-bold uppercase tracking-[.18em] text-[#ffcc66]">A plan for the life you already have</p>
            <h2 id="possibilities-heading" className="mt-4 text-3xl font-semibold leading-tight tracking-tight">Keep earning.<br />Keep learning.<br /><span className="text-[#ffcc66]">Keep moving forward.</span></h2>
            <div className="mt-8 space-y-4">{[
              { icon: Clock3, title: "Work around your commitments", copy: "Choose from available tutor slots that fit your routine." },
              { icon: Laptop, title: "Learn online, wherever you are", copy: "Join from a suitable place with internet access, across South Africa." },
              { icon: BookOpen, title: "Focus on the marks that matter", copy: "Build understanding and practise towards your subject goals." },
            ].map(({icon: Icon, title, copy}) => <div key={title} className="flex gap-3 rounded-2xl bg-white/5 p-4"><Icon aria-hidden="true" className="mt-1 size-5 shrink-0 text-[#ffcc66]" /><div><h3 className="text-sm font-bold">{title}</h3><p className="mt-1 text-sm leading-6 text-[#d0dcee]">{copy}</p></div></div>)}</div>
          </aside>
        </div>
      </section>

      <section id="exam-centre" className="scroll-mt-52 border-b border-[#ead9af] bg-[#fff8e7]" aria-labelledby="exam-centre-heading">
        <div className="mx-auto grid max-w-7xl gap-8 px-5 py-12 lg:grid-cols-[1.2fr_.8fr] lg:px-8 lg:py-16">
          <div>
            <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[.15em] text-[#765314]"><MapPin aria-hidden="true" className="size-4 shrink-0" />Your required first step</p>
            <h2 id="exam-centre-heading" className="mt-4 text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">Secure your exam centre.<br />Then start classes with us.</h2>
            <p className="mt-5 max-w-2xl text-base leading-8 text-[#624b22]"><strong>Before attending any Amaris class, you must secure an authorised examination centre</strong> and confirm your examination registration arrangements. Creating an Amaris account or booking tuition does not register you for a matric examination.</p>
            <ul className="mt-5 space-y-3 text-sm leading-7 text-[#624b22]">{["Confirm the NSC or Senior Certificate route and eligibility that apply to you.","Contact an authorised centre or your provincial education office about subjects, dates and registration requirements.","Secure your centre before attending Amaris lessons and keep your registration arrangements up to date."].map(item=><li key={item} className="flex gap-3"><Check aria-hidden="true" className="mt-1 size-4 shrink-0 text-[#765314]" /><span>{item}</span></li>)}</ul>
          </div>
          <aside className="self-start rounded-2xl border border-[#e6d1a0] bg-white p-6 sm:p-7">
            <h3 className="text-xl font-semibold">Exam registration and tuition are separate.</h3>
            <p className="mt-4 text-sm leading-7 text-[#624b22]">Amaris provides tutoring and academic preparation. We do not supply exam venues, register candidates for matric examinations or issue matric certificates.</p>
            <a href="https://www.education.gov.za/Curriculum/SeniorCertificate/SCRegistration.aspx" target="_blank" rel="noopener noreferrer" className={`mt-5 inline-flex min-h-11 items-center gap-2 text-sm font-bold text-[#184b9e] underline underline-offset-4 ${focus}`}>Official Senior Certificate guidance <span className="sr-only">(opens in a new tab)</span><ArrowRight aria-hidden="true" className="size-4 shrink-0" /></a>
            <a href="https://www.gov.za/services/services-residents/education-and-training/basic-education/register-rewrite-matric-subjects" target="_blank" rel="noopener noreferrer" className={`mt-3 inline-flex min-h-11 items-center gap-2 text-sm font-bold text-[#184b9e] underline underline-offset-4 ${focus}`}>Official matric rewrite guidance <span className="sr-only">(opens in a new tab)</span><ArrowRight aria-hidden="true" className="size-4 shrink-0" /></a>
          </aside>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-16 lg:px-8 lg:py-20" aria-labelledby="audience-heading">
        <p className="eyebrow">You do not have to put your life on hold</p>
        <h2 id="audience-heading" className="mt-4 max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">For the life you lead.<br />For the future you want.</h2>
        <p className="mt-5 max-w-2xl leading-8 text-[#53647d]">We welcome adults and anyone ready to work towards improved matric results. Bring your goal and your determination; let’s find a practical way to prepare.</p>
        <div className="mt-9 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{audiences.map(({title,detail,icon: Icon})=><article key={title} className="rounded-2xl border border-[#dce4ef] bg-white p-6"><Icon aria-hidden="true" className="size-8 text-[#1f5ab5]" /><h3 className="mt-5 text-lg font-semibold">{title}</h3><p className="mt-3 text-sm leading-7 text-[#53647d]">{detail}</p></article>)}</div>
      </section>

      <section id="study-plan" className="scroll-mt-52 border-y border-[#dce4ef] bg-white" aria-labelledby="steps-heading">
        <div className="mx-auto max-w-7xl px-5 py-16 lg:px-8 lg:py-20">
          <p className="eyebrow">A clear path from intention to preparation</p>
          <h2 id="steps-heading" className="mt-4 text-3xl font-semibold tracking-tight sm:text-4xl">Your matric upgrade journey.</h2>
          <div className="mt-9 grid gap-5 md:grid-cols-2">{steps.map(step=><article key={step.number} className="rounded-3xl border border-[#dce4ef] bg-[#f8faff] p-7"><span className="font-mono text-sm font-bold text-[#1f5ab5]">STEP {step.number}</span><h3 className="mt-5 text-xl font-semibold">{step.title}</h3><p className="mt-3 leading-7 text-[#53647d]">{step.description}</p></article>)}</div>
          <div className="mt-8 rounded-2xl bg-[#edf3ff] p-6 sm:p-8"><h3 className="text-xl font-semibold">Which subjects do you want to improve?</h3><p className="mt-3 max-w-3xl text-sm leading-7 text-[#53647d]">Ask about Mathematics, Mathematical Literacy, Physical Sciences, Life Sciences, Accounting, languages or another subject. We will confirm subject support, tutor availability, class times and applicable fees with you.</p><a href="/contact" className={`mt-5 inline-flex min-h-11 items-center gap-2 rounded-full bg-[#0b2a5b] px-5 py-3 text-sm font-bold text-white hover:bg-[#123d79] ${focus}`}>Discuss my subjects and study goals <ArrowRight aria-hidden="true" className="size-4 shrink-0" /></a></div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-9 px-5 py-16 lg:grid-cols-2 lg:items-center lg:px-8 lg:py-20" aria-labelledby="future-heading">
        <div><p className="eyebrow">More than a mark on a page</p><h2 id="future-heading" className="mt-4 text-3xl font-semibold tracking-tight sm:text-4xl">Give your next opportunity<br />a stronger starting point.</h2><p className="mt-5 leading-8 text-[#53647d]">Perhaps you want to apply for a diploma, pursue a degree or meet the entry requirements for a vocational programme. A stronger matric result may help you take that next step.</p><p className="mt-4 text-sm leading-7 text-[#53647d]">Admission depends on each institution and programme. Check the requirements for your goal; upgrading does not guarantee acceptance.</p></div>
        <div className="rounded-3xl bg-[#0b2a5b] p-7 text-white sm:p-9"><h3 className="text-2xl font-semibold">Prepare with purpose.</h3><ul className="mt-6 space-y-4">{["Revisit the concepts you need to understand","Work through subject-specific questions with a tutor","Practise past papers and examination technique","Build a realistic routine around available lesson times","Move forward one topic, one lesson and one goal at a time"].map(item=><li key={item} className="flex gap-3 text-sm leading-7 text-[#d0dcee]"><BadgeCheck aria-hidden="true" className="mt-1 size-5 shrink-0 text-[#ffcc66]" /><span>{item}</span></li>)}</ul></div>
      </section>

      <section className="mx-auto max-w-4xl px-5 pb-16 lg:px-8 lg:pb-20" aria-labelledby="questions-heading">
        <h2 id="questions-heading" className="text-3xl font-semibold tracking-tight">A few answers before you begin.</h2>
        <div className="mt-7 divide-y divide-[#dce4ef]">{faqs.map(([question,answer])=><details key={question} className="py-5"><summary className={`cursor-pointer text-base font-semibold leading-7 ${focus}`}>{question}</summary><p className="mt-3 text-sm leading-7 text-[#53647d]">{answer}</p></details>)}</div>
      </section>

      <section className="bg-[#07152d] text-white" aria-labelledby="start-heading">
        <div className="mx-auto max-w-7xl px-5 py-16 text-center lg:px-8 lg:py-20">
          <p className="text-xs font-bold uppercase tracking-[.18em] text-[#ffcc66]">Your ambition still deserves a chance</p>
          <h2 id="start-heading" className="mx-auto mt-5 max-w-3xl text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">You have worked for your life.<br /><span className="text-[#ffcc66]">Now work towards your next chapter.</span></h2>
          <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-[#d0dcee]">Secure your exam centre first. Then create your Amaris profile and explore available lessons that support your goals.</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3"><a href="/register" className={`inline-flex min-h-12 items-center gap-2 rounded-full bg-[#ffcc66] px-6 py-3.5 font-bold text-[#07152d] hover:bg-[#ffe09a] ${darkFocus}`}>Create my Amaris profile <ArrowRight aria-hidden="true" className="size-4 shrink-0" /></a><a href="/book-online-live-class" className={`inline-flex min-h-12 items-center rounded-full border border-white/40 px-6 py-3.5 font-semibold hover:bg-white/10 ${darkFocus}`}>Centre secured? Book a lesson</a></div>
          <a href="#exam-centre" className={`mt-6 inline-flex min-h-11 items-center text-sm font-semibold text-[#ffcc66] underline underline-offset-4 ${darkFocus}`}>I still need to secure my exam centre</a>
        </div>
      </section>
      <Footer />
    </main>
  );
}
