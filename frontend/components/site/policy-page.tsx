import { Download } from "lucide-react";
import policies from "@/content/policies.json";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";

type PolicyKey = keyof typeof policies;
type PolicyBlock = { type: "paragraph"; text: string } | { type: "list"; items: string[] };
type Policy = {
  title: string;
  summary: string;
  effectiveDate: string;
  sections: { heading: string; blocks: PolicyBlock[] }[];
};

const downloads: Record<PolicyKey, string> = {
  payment: "/policies/amaris-payment-policy.pdf",
  working: "/policies/amaris-how-we-work-policy.pdf",
};

export function PolicyPage({ policyKey }: { policyKey: PolicyKey }) {
  const policy = policies[policyKey] as Policy;

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <article className="mx-auto max-w-4xl px-5 py-16 lg:px-8 lg:py-24">
        <p className="eyebrow">Academy policy</p>
        <h1 className="section-title mt-4">{policy.title}</h1>
        <p className="mt-5 max-w-2xl text-lg leading-8 text-[#60708a]">{policy.summary}</p>
        <div className="mt-6 flex flex-wrap items-center gap-4">
          <p className="text-sm text-[#6a7890]">Effective {policy.effectiveDate}</p>
          <a
            href={downloads[policyKey]}
            download
            className="inline-flex items-center gap-2 rounded-full bg-[#0b2a5b] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#1f5bbd] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]"
          >
            <Download className="size-4" aria-hidden="true" />
            Download PDF
          </a>
        </div>
        <div className="mt-10 grid gap-5">
          {policy.sections.map((section, index) => (
            <section key={section.heading} className="rounded-2xl border border-[#dce4ef] bg-white p-6 sm:p-8">
              <h2 className="text-xl font-semibold text-[#0a1b36]">{index + 1}. {section.heading}</h2>
              <div className="mt-4 space-y-4 leading-7 text-[#5b6a82]">
                {section.blocks.map((block, blockIndex) =>
                  block.type === "list" ? (
                    <ul key={blockIndex} className="list-disc space-y-2 pl-6">
                      {block.items.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  ) : (
                    <p key={blockIndex}>{block.text}</p>
                  ),
                )}
              </div>
            </section>
          ))}
        </div>
        <p className="mt-8 text-sm leading-7 text-[#60708a]">
          Need help? <a href="/contact" className="font-semibold text-[#1f5bbd] underline underline-offset-2">Contact us</a>. See also our <a href="/terms" className="font-semibold text-[#1f5bbd] underline underline-offset-2">Student Terms</a> and <a href="/privacy" className="font-semibold text-[#1f5bbd] underline underline-offset-2">Privacy Policy</a>.
        </p>
      </article>
      <Footer />
    </main>
  );
}
