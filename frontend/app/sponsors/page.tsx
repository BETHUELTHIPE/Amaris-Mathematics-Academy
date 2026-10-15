import type { Metadata } from "next";
import { ArrowDown, ArrowUpRight, BookOpen, Heart, Layers3, ShieldCheck, Sparkles } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { getManagedBrand } from "@/lib/cms";
import { getSponsorshipPaymentUrl, sponsorshipMode } from "@/lib/sponsorship";

export const metadata: Metadata = {
  title: "Sponsor the project | Amaris Mathematics Academy",
  description: "Support the next chapter of Amaris Mathematics Academy. Help us build clear mathematics resources and a stronger learning platform.",
};

const priorities = [
  { icon: BookOpen, number: "01", title: "More moments of clarity", copy: "Help us develop clear explanations, worked examples and practice resources that make complex ideas easier to understand." },
  { icon: Layers3, number: "02", title: "A stronger place to learn", copy: "Support the ongoing development and upkeep of the platform, so learning stays organised and accessible." },
  { icon: Sparkles, number: "03", title: "Room for the next chapter", copy: "Contribute towards the academy’s growth and the development of new mathematics learning experiences." },
];

export default async function SponsorsPage() {
  const brand = await getManagedBrand();
  const sandbox = sponsorshipMode() === "sandbox";
  const paymentUrl = getSponsorshipPaymentUrl();
  const enquiryUrl = `${brand.emailHref}?subject=${encodeURIComponent("Amaris project sponsorship enquiry")}`;

  return (
    <main className="min-h-screen bg-[#f5f7fb] text-[#07152d]">
      <Header />
      <section className="relative overflow-hidden bg-[#07152d] text-white">
        <div aria-hidden="true" className="graph-paper absolute inset-0 opacity-20" />
        <div className="relative mx-auto grid max-w-7xl gap-12 px-5 py-16 lg:grid-cols-[1.2fr_.8fr] lg:items-center lg:px-8 lg:py-24">
          <div>
            <p className="text-xs font-bold uppercase tracking-[.18em] text-[#ffcc66]">Small acts. Lasting possibilities.</p>
            <h1 className="mt-5 max-w-3xl text-5xl font-semibold leading-[1.05] tracking-[-.05em] sm:text-7xl">Help the next<br />idea <span className="text-[#ffcc66]">add up.</span></h1>
            <p className="mt-6 max-w-xl text-lg leading-8 text-white/75">Behind every confident learner is a moment when mathematics finally makes sense. Sponsor the Amaris project and help us create more of those moments.</p>
            <a href="#contribute" className="mt-8 inline-flex min-h-12 items-center gap-3 rounded-full bg-[#ffcc66] px-7 py-4 font-bold text-[#07152d] transition hover:bg-[#ffda8f] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white">Become a sponsor <ArrowDown className="size-4" /></a>
          </div>
          <div aria-hidden="true" className="relative mx-auto flex aspect-square w-full max-w-sm items-center justify-center rounded-full border border-white/15 bg-white/[.03]">
            <div className="absolute inset-8 rounded-full border border-dashed border-white/20" />
            <div className="relative text-center"><Heart className="mx-auto size-12 text-[#ffcc66]" strokeWidth={1.5} /><p className="mt-6 text-6xl font-semibold tracking-[-.06em]">You +<br /><span className="text-[#ffcc66]">possibility.</span></p><p className="mt-5 font-mono text-xs uppercase tracking-[.18em] text-white/65">A little support. A new beginning.</p></div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-16 lg:px-8 lg:py-20" aria-labelledby="impact-heading">
        <p className="eyebrow">The purpose behind your support</p>
        <h2 id="impact-heading" className="section-title mt-4 max-w-3xl">Invest in the work behind the learning.</h2>
        <p className="mt-5 max-w-2xl leading-8 text-[#60708a]">Your contribution supports the Amaris Mathematics Academy project and its continued development. These are the areas your support can help move forward.</p>
        <div className="mt-10 grid gap-5 md:grid-cols-3">{priorities.map(({ icon: Icon, number, title, copy }) => <article key={number} className="rounded-3xl border border-[#dce4ef] bg-white p-7"><div className="flex items-center justify-between"><span className="grid size-12 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]"><Icon className="size-6" /></span><span className="font-mono text-sm text-[#60708a]">{number}</span></div><h3 className="mt-7 text-2xl font-semibold tracking-tight">{title}</h3><p className="mt-4 text-sm leading-7 text-[#60708a]">{copy}</p></article>)}</div>
      </section>

      <section id="contribute" className="mx-auto grid max-w-7xl scroll-mt-8 gap-10 px-5 pb-16 lg:grid-cols-[1fr_1fr] lg:px-8 lg:pb-24" aria-labelledby="contribute-heading">
        <div className="rounded-3xl bg-[#0b2a5b] p-7 text-white sm:p-10">
          <Heart className="size-8 text-[#ffcc66]" />
          <p className="mt-7 text-xs font-bold uppercase tracking-[.18em] text-[#ffcc66]">Sponsor the project</p>
          <h2 id="contribute-heading" className="mt-4 text-4xl font-semibold tracking-[-.04em]">Make a contribution.<br />Be part of what comes next.</h2>
          <p className="mt-5 leading-8 text-white/75">Every contribution is appreciated. Continue to PayFast to review the payment details and complete your sponsorship securely.</p>
          {sandbox ? <form action="/sponsors/checkout" method="get" className="mt-8"><div className="rounded-xl border border-[#ffcc66]/40 bg-[#ffcc66]/10 p-4 text-sm leading-7 text-[#ffdd99]"><strong>Sandbox testing is active.</strong> No real money is charged or received.</div><label htmlFor="sponsor-amount" className="mt-5 block text-sm font-semibold">Test contribution amount (ZAR)</label><input id="sponsor-amount" name="amount" type="number" min="5" max="100000" step="0.01" defaultValue="100" required className="mt-2 min-h-12 w-full rounded-xl border border-white/30 bg-white px-4 py-3 text-lg text-[#07152d]" /><p className="mt-2 text-xs text-white/70">R5–R100,000 · one test contribution</p><button type="submit" className="mt-5 min-h-12 w-full rounded-full bg-[#ffcc66] px-6 py-4 font-bold text-[#07152d] transition hover:bg-[#ffda8f]">Test sponsorship with PayFast</button></form> : paymentUrl ? <a href={paymentUrl} className="mt-8 inline-flex min-h-12 w-full items-center justify-center gap-3 rounded-full bg-[#ffcc66] px-6 py-4 font-bold text-[#07152d] transition hover:bg-[#ffda8f] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white">Support with PayFast <ArrowUpRight className="size-5" /></a> : <div className="mt-8 rounded-2xl border border-white/20 bg-white/5 p-5"><p className="font-semibold">Online sponsorship is opening soon.</p><p className="mt-2 text-sm leading-7 text-white/75">Contact us to discuss supporting the project while we prepare online contributions.</p><a href={enquiryUrl} className="mt-4 inline-flex min-h-11 items-center gap-2 font-bold text-[#ffcc66] underline underline-offset-4">Enquire about sponsorship <ArrowUpRight className="size-4" /></a></div>}
          <p className="mt-5 flex items-start gap-2 text-xs leading-6 text-white/70"><ShieldCheck className="mt-1 size-4 shrink-0" />Payment details are entered on PayFast’s website. Amaris does not collect your card details on this page.</p>
        </div>
        <div className="py-3 lg:p-6">
          <h2 className="text-3xl font-semibold tracking-tight">A little clarity before you give.</h2>
          <div className="mt-7 divide-y divide-[#dce4ef]">
            {[
              ["What does my contribution support?", "Contributions support the academy project as a whole, including content, platform upkeep and continued development. They are not allocated to a particular learner or activity unless separately agreed."],
              ["Do I need a student account?", "No. Individuals, families and businesses are welcome to support the project without registering as students."],
              ["Does sponsorship include course access?", "Sponsorship is voluntary support for the project. Course enrolment is purchased separately, and contributions do not automatically provide course access or a tax-deductible donation certificate."],
              ["Can my business get involved?", "Yes. Contact us to discuss a larger contribution, an ongoing partnership or any recognition you would like to arrange before making a payment."],
            ].map(([question, answer]) => <details key={question} className="group py-5"><summary className="cursor-pointer text-base font-semibold leading-7 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#1f5bbd]">{question}</summary><p className="mt-3 text-sm leading-7 text-[#60708a]">{answer}</p></details>)}
          </div>
          <p className="mt-7 text-sm leading-7 text-[#60708a]">Let’s build something meaningful together. <a href={enquiryUrl} className="font-bold text-[#1f5bbd] underline underline-offset-4">Talk to us about sponsorship.</a></p>
        </div>
      </section>
      <Footer />
    </main>
  );
}
