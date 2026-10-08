import { Download } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import policies from "@/lib/policies.json";

export function PolicyPage({ kind }: { kind: "payment" | "working" }) {
  const policy = policies[kind];
  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <article className="mx-auto max-w-4xl px-5 py-16 lg:px-8 lg:py-24">
        <p className="eyebrow">Academy policies</p>
        <h1 className="section-title mt-4">{policy.title}</h1>
        <p className="mt-4 text-sm text-[#6a7890]">Effective {policy.effective}</p>
        <p className="mt-6 max-w-3xl text-lg leading-8 text-[#4d5d76]">{policy.intro}</p>
        <a
          href={`/policies/${kind}-policy.pdf`}
          download
          className="mt-7 inline-flex items-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white"
        >
          <Download className="size-4" /> Download PDF
        </a>
        <div className="mt-10 grid gap-5">
          {policy.sections.map((section) => (
            <section key={section.title} className="rounded-2xl border border-[#dce4ef] bg-white p-6">
              <h2 className="text-xl font-semibold">{section.title}</h2>
              <p className="mt-3 leading-7 text-[#5b6a82]">{section.body}</p>
            </section>
          ))}
        </div>
      </article>
      <Footer />
    </main>
  );
}
