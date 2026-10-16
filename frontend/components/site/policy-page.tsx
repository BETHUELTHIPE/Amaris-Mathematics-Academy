import { Download } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { BrandDocumentFooter, BrandLetterhead } from "@/components/documents/brand-letterhead";
import policies from "@/lib/policies.json";

export function PolicyPage({ kind }: { kind: "payment" | "working" }) {
  const policy = policies[kind];
  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <div className="print-hidden"><Header /></div>
      <article className="document-preview mx-auto max-w-4xl px-4 py-10 sm:px-5 sm:py-14 lg:px-8 lg:py-20">
        <div className="print-sheet flex flex-col overflow-hidden rounded-2xl bg-white shadow-[0_20px_55px_rgba(7,21,45,.1)] ring-1 ring-[#dce4ef] print:rounded-none print:shadow-none print:ring-0">
          <BrandLetterhead documentLabel={policy.title} />
          <div className="min-w-0 flex-1 px-5 py-9 sm:px-10">
            <p className="eyebrow">Academy policies</p>
            <h1 className="mt-4 break-words text-3xl font-semibold tracking-tight text-[#07152d] sm:text-4xl">{policy.title}</h1>
            <p className="mt-4 text-sm text-[#6a7890]">Effective {policy.effective}</p>
            <p className="mt-6 max-w-3xl text-base leading-8 text-[#4d5d76] sm:text-lg">{policy.intro}</p>
            <a href={`/policies/${kind}-policy.pdf`} download className="print-hidden mt-7 inline-flex min-h-12 items-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white">
              <Download aria-hidden="true" className="size-4" /> Download letterheaded PDF
            </a>
            <div className="mt-10 grid gap-6">
              {policy.sections.map((section) => (
                <section key={section.title} className="break-inside-avoid border-t border-[#dce4ef] pt-5">
                  <h2 className="text-xl font-semibold text-[#07152d]">{section.title}</h2>
                  <p className="mt-3 break-words leading-7 text-[#43526a]">{section.body}</p>
                </section>
              ))}
            </div>
          </div>
          <BrandDocumentFooter reference={policy.title} />
        </div>
      </article>
      <div className="print-hidden"><Footer /></div>
    </main>
  );
}
