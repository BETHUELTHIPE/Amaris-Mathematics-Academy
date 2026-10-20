import type { Metadata } from "next";
import { ArrowDown, ArrowRight, ArrowUpRight, BookOpen, BrainCircuit, BriefcaseBusiness, Check, ChevronDown, Code2, Database, GraduationCap, Lightbulb, Mail, Network, ShieldAlert, Users } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { getManagedBrand } from "@/lib/cms";
import { aiCurriculum, aiQualification } from "@/lib/ai-software-developer";

const pageUrl = "https://amaris-mathematics-academy-live-students.onrender.com/ai-software-developer";
export const metadata: Metadata = {
  title: "Artificial Intelligence Software Developer | NQF Level 5",
  description: "Explore the Occupational Certificate: Artificial Intelligence Software Developer, NQF Level 5, 209 credits. View all 26 modules. Amaris is not yet accredited; accreditation application in progress. Enquiries only.",
  alternates: { canonical: pageUrl },
  openGraph: {
    type: "website", url: pageUrl,
    title: "Build your future in AI | Amaris Mathematics Academy",
    description: "Explore the complete 26-module qualification structure. Planned programme: Amaris is not yet accredited and is applying for accreditation. Enquiries only.",
  },
};

const focus = "focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#1f5bbd]";
const darkFocus = "focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#ffcc66]";
const audiences = [
  { icon: GraduationCap, title: "School leavers", copy: "Have an NQF Level 4 qualification and a curiosity for technology? Explore a practical direction for your next chapter." },
  { icon: BriefcaseBusiness, title: "Career changers", copy: "Bring your experience of real problems into a field that combines logic, creativity and software development." },
  { icon: Users, title: "Working professionals", copy: "Explore the foundations behind AI tools and how intelligent software can help solve problems in your industry." },
  { icon: Code2, title: "Aspiring developers", copy: "Connect your interest in coding with data, machine learning and the discipline of testing what you build." },
];
const outcomes = [
  ["Ask the right questions", "Gather and interpret data from different sources to define a real-world AI problem."],
  ["Design a solution", "Analyse the data and document a solution that responds to the problem."],
  ["Choose a learning approach", "Match the problem to suitable AI methods and algorithms."],
  ["Train and evaluate models", "Train a model within a chosen framework and monitor its accuracy."],
  ["Build with the right tools", "Use suitable machine-learning libraries and systems to develop a solution."],
  ["Deploy and improve", "Implement the solution on a chosen platform and evaluate how it performs in use."],
];
const faqs = [
  ["Is Amaris accredited to offer this qualification?", "No. Amaris Mathematics Academy is not yet accredited by QCTO to offer this qualification. We are in the process of applying for accreditation. Approval has not been granted. This page introduces the proposed programme and invites interest enquiries only."],
  ["Can I enrol or pay for a place now?", "No. We are not opening enrolment or accepting payments for this qualification through this page. An enquiry does not reserve a place or register you as a learner. Any future offering depends on accreditation approval and QCTO confirmation of an applicable, valid enrolment route."],
  ["What is the minimum entry requirement?", "The official qualification record specifies an NQF Level 4 qualification. Recognition of Prior Learning may be available through appropriately accredited providers and approved workplaces; Amaris is not currently offering RPL for this qualification. Future admission requirements will be confirmed before any approved intake."],
  ["Why does the official record show an end date?", "The SAQA record shows that the qualification passed its registration end date on 31 December 2025, with a last enrolment date of 31 December 2026 and last achievement date of 31 December 2029. These are qualification dates, not Amaris intake dates. They do not authorise Amaris to enrol learners or extend any deadline. We must confirm the applicable route with QCTO before offering an intake."],
  ["What are the fees, duration and class format?", "Fees, duration, start dates and delivery arrangements have not been announced. We will confirm these only once the accreditation position and valid qualification route allow us to make a reliable offer. Do not make payments or plans on the assumption that a place or intake is available."],
  ["Is workplace experience included in the qualification?", "Yes. The official structure includes 60 credits of compulsory work experience alongside knowledge and practical skills modules. Amaris has not announced workplace arrangements and does not guarantee a placement or employment. Those arrangements would need to be confirmed for any future approved offering."],
  ["Does attendance alone earn the certificate?", "No. The qualification requires completion of its knowledge, practical skills and work experience components, followed by the required external integrated summative assessment through the relevant QCTO assessment arrangements. Amaris is not currently delivering or issuing this qualification."],
];

export default async function AiSoftwareDeveloperPage() {
  const brand = await getManagedBrand();
  const enquiryEmail = `${brand.emailHref}?subject=${encodeURIComponent("Interest enquiry: AI Software Developer NQF Level 5")}`;
  return (
    <main className="min-h-screen bg-[#f5f7fb] text-[#0a1b36]">
      <Header />
      <section className="relative overflow-hidden bg-[#07152d] text-white" aria-labelledby="ai-title">
        <div className="graph-paper pointer-events-none absolute inset-0 opacity-20" aria-hidden="true" />
        <div className="relative mx-auto grid max-w-7xl gap-12 px-5 py-16 lg:grid-cols-[1.2fr_.8fr] lg:items-center lg:px-8 lg:py-24">
          <div>
            <p className="inline-flex items-start gap-2 text-xs font-bold uppercase leading-6 tracking-[.16em] text-[#ffcc66]"><BrainCircuit aria-hidden="true" className="mt-1 size-4 shrink-0" />Planned programme · NQF Level 5</p>
            <h1 id="ai-title" className="mt-6 text-4xl font-semibold leading-[1.06] tracking-[-.045em] sm:text-6xl lg:text-7xl">Don’t just use AI.<br /><span className="text-[#ffcc66]">Learn how to build it.</span></h1>
            <p className="mt-6 text-lg font-semibold leading-8">{aiQualification.title}</p>
            <p className="mt-4 max-w-2xl text-base leading-8 text-[#d0dcee]">Start with a question. Explore the data. Build something that makes a difference. Discover a qualification pathway that connects mathematics, Python and machine learning with practical problem solving.</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <a href="#enquire" className={`inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-[#ffcc66] px-6 py-3.5 font-bold text-[#07152d] hover:bg-[#ffe09a] motion-safe:transition-transform motion-safe:hover:-translate-y-1 ${darkFocus}`}>Express interest <ArrowRight aria-hidden="true" className="size-4 shrink-0" /></a>
              <a href="#curriculum" className={`inline-flex min-h-12 items-center justify-center gap-2 rounded-full border border-white/40 px-6 py-3.5 font-semibold hover:bg-white/10 ${darkFocus}`}>Explore the curriculum <ArrowDown aria-hidden="true" className="size-4 shrink-0" /></a>
            </div>
            <p className="mt-6 flex items-start gap-2 text-sm leading-6 text-[#ffdc96]"><ShieldAlert aria-hidden="true" className="mt-1 size-5 shrink-0" /><span><strong>Not yet accredited.</strong> Amaris is applying for accreditation. Enquiries only; enrolment is not open.</span></p>
          </div>
          <aside className="rounded-3xl border border-white/20 bg-white/5 p-6 sm:p-8" aria-labelledby="pathway-heading">
            <div className="flex items-center justify-between gap-4"><p className="text-xs font-bold uppercase tracking-[.18em] text-[#ffcc66]">From curiosity to capability</p><Network aria-hidden="true" className="size-7 shrink-0 text-[#ffcc66]" /></div>
            <h2 id="pathway-heading" className="mt-5 text-3xl font-semibold leading-tight tracking-tight">Think it through.<br />Build it with purpose.<br /><span className="text-[#ffcc66]">Keep improving it.</span></h2>
            <div className="mt-7 space-y-3">{[
              { icon: Database, title: "Understand the data", text: "Mathematics · Statistics · SQL" },
              { icon: Code2, title: "Develop the solution", text: "Python · Machine learning · Deep learning" },
              { icon: Lightbulb, title: "Make it work in practice", text: "Design · Testing · Responsible deployment" },
            ].map(({ icon: Icon, title, text }, index) => <div key={title} className="flex gap-4 rounded-2xl border border-white/10 bg-white/5 p-4"><span className="mt-1 text-xs font-bold text-[#ffcc66]">0{index + 1}</span><div className="min-w-0 flex-1"><h3 className="font-semibold">{title}</h3><p className="mt-1 text-sm leading-6 text-[#d0dcee]">{text}</p></div><Icon aria-hidden="true" className="mt-1 size-5 shrink-0 text-[#ffcc66]" /></div>)}</div>
            <dl className="mt-7 grid grid-cols-3 gap-3 border-t border-white/20 pt-6">{[["5", "NQF level"], ["209", "Credits"], ["26", "Modules"]].map(([value, label]) => <div key={label}><dt className="text-xs leading-5 text-[#d0dcee]">{label}</dt><dd className="mt-1 text-2xl font-semibold text-[#ffcc66]">{value}</dd></div>)}</dl>
            <p className="mt-4 text-xs leading-6 text-[#d0dcee]">Official qualification facts · SAQA ID 118792<br />These facts do not indicate Amaris accreditation.</p>
          </aside>
        </div>
      </section>

      <section id="accreditation" className="scroll-mt-52 border-b border-[#ead9af] bg-[#fff8e7]" aria-labelledby="accreditation-heading">
        <div className="mx-auto grid max-w-7xl gap-8 px-5 py-12 lg:grid-cols-[1.2fr_.8fr] lg:px-8 lg:py-16">
          <div>
            <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[.15em] text-[#765314]"><ShieldAlert aria-hidden="true" className="size-5 shrink-0" />Please read before enquiring</p>
            <h2 id="accreditation-heading" className="mt-4 text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">Accreditation application in progress.<br />Not accredited yet.</h2>
            <p className="mt-5 text-base leading-8 text-[#624b22]"><strong>Amaris Mathematics Academy is not yet accredited by QCTO to offer this qualification.</strong> We are in the process of applying for accreditation. Approval has not been granted.</p>
            <p className="mt-4 text-sm leading-7 text-[#624b22]">This is an introduction to a proposed programme and its official qualification structure. We are inviting interest enquiries only. We are not opening enrolment, accepting qualification fees or promising an intake, a certificate or accreditation approval.</p>
            <p className="mt-4 text-sm leading-7 text-[#624b22]">Any future offering depends on accreditation approval and QCTO confirmation of an applicable, valid enrolment route. Expressing interest does not register you as a learner or reserve a place.</p>
          </div>
          <aside className="self-start rounded-2xl border border-[#e6d1a0] bg-white p-6 sm:p-7" aria-labelledby="official-status-heading">
            <h3 id="official-status-heading" className="text-xl font-semibold">Official qualification status</h3>
            <p className="mt-3 text-sm leading-7 text-[#624b22]">The SAQA record shows this qualification has passed its registration end date. This is separate from Amaris’s accreditation application.</p>
            <dl className="mt-4 space-y-3 text-sm">{[["Registration ended", "31 December 2025"], ["Last enrolment date", "31 December 2026"], ["Last achievement date", "31 December 2029"]].map(([term, date]) => <div key={term} className="border-t border-[#ead9af] pt-3"><dt className="text-[#624b22]">{term}</dt><dd className="mt-1 font-bold">{date}</dd></div>)}</dl>
            <p className="mt-4 text-xs leading-6 text-[#624b22]">These dates are not Amaris intake dates and do not extend any enrolment window. Source: SAQA. Checked {aiQualification.checked}.</p>
            <a href={aiQualification.sources.saqa} target="_blank" rel="noopener noreferrer" className={`mt-3 inline-flex min-h-11 items-center gap-2 text-sm font-bold text-[#184b9e] underline underline-offset-4 ${focus}`}>Check the official record <ArrowUpRight aria-hidden="true" className="size-4 shrink-0" /><span className="sr-only">(opens in a new tab)</span></a>
          </aside>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-16 lg:px-8 lg:py-20" aria-labelledby="audience-heading">
        <p className="text-xs font-bold uppercase tracking-[.16em] text-[#1f5bbd]">A new direction starts with a decision</p>
        <h2 id="audience-heading" className="mt-4 max-w-3xl text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">Your curiosity could become<br className="hidden sm:block" /> your next professional skill.</h2>
        <p className="mt-5 max-w-3xl text-base leading-8 text-[#526781]">You do not need to have your whole future mapped out to explore it. If you enjoy asking why, spotting patterns and solving problems, take a closer look at what AI development involves.</p>
        <div className="mt-9 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{audiences.map(({ icon: Icon, title, copy }) => <article key={title} className="rounded-2xl border border-[#dce4ef] bg-white p-6 motion-safe:transition-transform motion-safe:duration-300 motion-safe:hover:-translate-y-1"><Icon aria-hidden="true" className="size-7 text-[#1f5bbd]" /><h3 className="mt-5 text-lg font-semibold">{title}</h3><p className="mt-3 text-sm leading-7 text-[#526781]">{copy}</p></article>)}</div>
        <p className="mt-5 text-sm leading-7 text-[#526781]"><strong>Minimum entry in the official record:</strong> an NQF Level 4 qualification. Any future admission process must be confirmed before an approved intake.</p>
      </section>

      <section className="border-y border-[#dce4ef] bg-white" aria-labelledby="outcomes-heading">
        <div className="mx-auto max-w-7xl px-5 py-16 lg:px-8 lg:py-20">
          <div className="grid gap-8 lg:grid-cols-[.8fr_1.2fr]">
            <div><p className="text-xs font-bold uppercase tracking-[.16em] text-[#1f5bbd]">More than knowing the buzzwords</p><h2 id="outcomes-heading" className="mt-4 text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">Build the thinking.<br />Then build the technology.</h2><p className="mt-5 text-base leading-8 text-[#526781]">Behind a useful AI solution is sound reasoning. Mathematics, statistics and careful testing give your code a stronger foundation. That connection is at the heart of our vision for AI learning at Amaris.</p><p className="mt-4 text-sm leading-7 text-[#526781]">The official qualification aims to develop the following capabilities. These describe qualification outcomes, rather than a current Amaris course offer or a guarantee of employment.</p></div>
            <div className="grid gap-5 sm:grid-cols-2">{outcomes.map(([title, copy], index) => <article key={title} className="rounded-2xl bg-[#f5f7fb] p-6"><p className="text-xs font-bold tracking-widest text-[#1f5bbd]">0{index + 1}</p><h3 className="mt-3 text-lg font-semibold">{title}</h3><p className="mt-2 text-sm leading-7 text-[#526781]">{copy}</p></article>)}</div>
          </div>
        </div>
      </section>

      <section id="curriculum" className="mx-auto max-w-7xl scroll-mt-52 px-5 py-16 lg:px-8 lg:py-20" aria-labelledby="curriculum-heading">
        <p className="text-xs font-bold uppercase tracking-[.16em] text-[#1f5bbd]">The complete compulsory module structure</p>
        <h2 id="curriculum-heading" className="mt-4 text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">26 modules. Three connected components.<br /><span className="text-[#1f5bbd]">One practical direction.</span></h2>
        <p className="mt-5 max-w-3xl text-base leading-8 text-[#526781]">Explore every compulsory module in the official qualification record: 86 knowledge credits, 63 practical skills credits and 60 work experience credits, totalling 209 credits. All three components are required.</p>
        <div className="mt-8 flex flex-wrap gap-3 text-xs font-semibold text-[#184b9e]">{["SAQA ID 118792", "NQF Level 5", "Curriculum 251201-002-00-00"].map(item => <span key={item} className="rounded-full border border-[#cbd9ec] bg-white px-4 py-2 leading-6">{item}</span>)}</div>
        <div className="mt-8 space-y-5">{aiCurriculum.map((group, index) => <details key={group.id} open className="group rounded-2xl border border-[#dce4ef] bg-white" data-curriculum={group.id}>
          <summary className={`flex min-h-24 cursor-pointer list-none items-center gap-4 rounded-2xl p-5 sm:p-7 [&::-webkit-details-marker]:hidden ${focus}`}>
            <span className="hidden size-12 shrink-0 items-center justify-center rounded-xl bg-[#eaf1fb] text-lg font-bold text-[#1f5bbd] sm:flex">0{index + 1}</span>
            <span className="min-w-0 flex-1"><h3 className="text-xl font-semibold">{group.title}</h3><span className="mt-1 block text-sm leading-6 text-[#526781]">{group.modules.length} modules · {group.credits} credits<span className="mt-1 hidden sm:block">{group.subtitle}</span></span></span>
            <ChevronDown aria-hidden="true" className="size-5 shrink-0 text-[#1f5bbd] group-open:rotate-180 motion-safe:transition-transform" />
          </summary>
          <ol className="border-t border-[#dce4ef] px-5 sm:px-7">{group.modules.map(module => <li key={module.code} className="grid gap-3 border-b border-[#e6ecf5] py-5 last:border-0 sm:grid-cols-[1fr_auto] sm:items-center" data-module-code={module.code}>
            <div className="min-w-0"><p className="break-words text-xs font-semibold tracking-wide text-[#526781]">{module.code}</p><h4 className="mt-2 text-base font-semibold leading-7">{module.title}</h4></div>
            <p className="flex shrink-0 flex-wrap gap-2 text-xs font-semibold"><span className="rounded-md bg-[#eaf1fb] px-3 py-2 text-[#184b9e]">NQF {module.level}</span><span className="rounded-md bg-[#f5f7fb] px-3 py-2 text-[#344d6b]">{module.credits} {module.credits === 1 ? "credit" : "credits"}</span></p>
          </li>)}</ol>
        </details>)}</div>
        <aside className="mt-7 rounded-2xl border border-[#cbd9ec] bg-[#eaf1fb] p-6 text-sm leading-7 text-[#344d6b]" aria-label="Curriculum sources">
          <p><strong>Source acknowledgement:</strong> all compulsory module titles, codes, NQF levels and credits above are reproduced from SAQA’s official qualification record 118792. Qualification quality council: QCTO. Development and assessment quality partner: MICT SETA. Checked {aiQualification.checked}.</p>
          <p className="mt-3">This page contains the complete module structure and an overview of the qualification. Detailed QCTO module specifications, topic weightings and assessment criteria are in the official curriculum and external assessment documents available through the QCTO directory.</p>
          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2"><a href={aiQualification.sources.saqa} target="_blank" rel="noopener noreferrer" className={`inline-flex min-h-11 items-center gap-2 font-bold text-[#184b9e] underline underline-offset-4 ${focus}`}>SAQA qualification record <ArrowUpRight aria-hidden="true" className="size-4" /><span className="sr-only">(opens in a new tab)</span></a><a href={aiQualification.sources.qcto} target="_blank" rel="noopener noreferrer" className={`inline-flex min-h-11 items-center gap-2 font-bold text-[#184b9e] underline underline-offset-4 ${focus}`}>QCTO curriculum directory <ArrowUpRight aria-hidden="true" className="size-4" /><span className="sr-only">(opens in a new tab)</span></a></div>
          <p className="mt-2 text-xs leading-6">Search for SAQA ID 118792 or curriculum code 251201-002-00-00. Consult QCTO about the current qualification route and the registration dates shown above.</p>
        </aside>
      </section>

      <section className="border-y border-[#dce4ef] bg-white" aria-labelledby="assessment-heading">
        <div className="mx-auto grid max-w-7xl gap-8 px-5 py-16 lg:grid-cols-2 lg:px-8 lg:py-20">
          <div><p className="text-xs font-bold uppercase tracking-[.16em] text-[#1f5bbd]">How the qualification comes together</p><h2 id="assessment-heading" className="mt-4 text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">Learn it. Apply it.<br />Demonstrate it.</h2><p className="mt-5 text-base leading-8 text-[#526781]">This is an occupational qualification, so workplace application matters alongside knowledge and practical skills. Completing lessons alone is not enough to earn the certificate.</p></div>
          <div className="space-y-4">{[
            { icon: BookOpen, title: "Knowledge and practical assessment", copy: "The curriculum includes internal assessment of understanding and applied skills against the required criteria." },
            { icon: BriefcaseBusiness, title: "Compulsory workplace experience", copy: "Learners must complete the work experience component. Future workplace arrangements would need confirmation; Amaris does not guarantee a placement." },
            { icon: Check, title: "External integrated summative assessment", copy: "Completion of the required components leads to eligibility for the EISA through the relevant QCTO assessment arrangements. Successful assessment is required for the qualification award." },
          ].map(({ icon: Icon, title, copy }) => <div key={title} className="flex gap-4 rounded-2xl bg-[#f5f7fb] p-6"><Icon aria-hidden="true" className="mt-1 size-5 shrink-0 text-[#1f5bbd]" /><div><h3 className="font-semibold">{title}</h3><p className="mt-2 text-sm leading-7 text-[#526781]">{copy}</p></div></div>)}</div>
        </div>
      </section>

      <section className="mx-auto max-w-4xl px-5 py-16 lg:px-8 lg:py-20" aria-labelledby="faq-heading">
        <p className="text-xs font-bold uppercase tracking-[.16em] text-[#1f5bbd]">Make an informed next move</p>
        <h2 id="faq-heading" className="mt-4 text-3xl font-semibold tracking-tight sm:text-4xl">Your questions, answered clearly.</h2>
        <div className="mt-8 space-y-3">{faqs.map(([question, answer]) => <details key={question} className="group rounded-2xl border border-[#dce4ef] bg-white"><summary className={`flex min-h-16 cursor-pointer list-none items-center justify-between gap-4 rounded-2xl p-5 text-base font-semibold leading-7 [&::-webkit-details-marker]:hidden ${focus}`}>{question}<ChevronDown aria-hidden="true" className="size-5 shrink-0 text-[#1f5bbd] group-open:rotate-180 motion-safe:transition-transform" /></summary><p className="px-5 pb-6 text-sm leading-7 text-[#526781]">{answer}</p></details>)}</div>
      </section>

      <section id="enquire" className="scroll-mt-52 bg-[#07152d] text-white" aria-labelledby="enquire-heading">
        <div className="mx-auto grid max-w-7xl gap-8 px-5 py-16 lg:grid-cols-[1.2fr_.8fr] lg:items-center lg:px-8 lg:py-20">
          <div><p className="text-xs font-bold uppercase tracking-[.16em] text-[#ffcc66]">Curiosity is a powerful first step</p><h2 id="enquire-heading" className="mt-4 text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">Imagine what you could build.<br /><span className="text-[#ffcc66]">Start with a conversation.</span></h2><p className="mt-5 max-w-2xl text-base leading-8 text-[#d0dcee]">Tell us what draws you to AI and what you would like to learn. Ask about the proposed programme and our accreditation progress before making any study plans.</p></div>
          <div className="rounded-3xl border border-white/20 bg-white/5 p-6 sm:p-8"><h3 className="text-xl font-semibold">Interested in the AI pathway?</h3><p className="mt-3 text-sm leading-7 text-[#d0dcee]">Use our contact page, choose “Course guidance” and mention “AI Software Developer”, or send us an email.</p><div className="mt-5 flex flex-col gap-3"><a href="/contact" className={`inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-[#ffcc66] px-6 py-3 font-bold text-[#07152d] hover:bg-[#ffe09a] ${darkFocus}`}>Enquire about the planned programme <ArrowRight aria-hidden="true" className="size-4 shrink-0" /></a><a href={enquiryEmail} className={`inline-flex min-h-12 items-center justify-center gap-2 rounded-full border border-white/40 px-6 py-3 font-semibold hover:bg-white/10 ${darkFocus}`}><Mail aria-hidden="true" className="size-4 shrink-0" />Email your interest</a></div><p className="mt-5 text-sm leading-6 text-[#ffdc96]"><strong>Not yet accredited · Application in progress.</strong><br />Enquiries only. No enrolment, place reservation or qualification payment.</p></div>
        </div>
      </section>
      <Footer />
    </main>
  );
}
