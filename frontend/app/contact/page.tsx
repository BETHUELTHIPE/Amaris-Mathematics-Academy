import type { Metadata } from "next";
import { Clock3, Mail, MapPin, MessageCircle, Phone } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { EnquiryForm } from "@/components/site/enquiry-form";
import { getManagedBrand } from "@/lib/cms";

export const metadata: Metadata = {
  title: "Contact Us",
  description: "Contact Amaris Mathematics Academy for course guidance, enrolment, payment or technical support.",
};

export default async function ContactPage() {
  const academyBrand = await getManagedBrand();
  const contactCards = [
    { Icon: Phone, label: "Call us", value: academyBrand.phoneDisplay, href: academyBrand.phoneHref },
    { Icon: MessageCircle, label: "WhatsApp", value: academyBrand.whatsappDisplay, href: academyBrand.whatsappHref },
    { Icon: Mail, label: "Email us", value: academyBrand.email, href: academyBrand.emailHref },
    { Icon: Clock3, label: "Support hours", value: academyBrand.hours },
    { Icon: MapPin, label: "Registered office", value: academyBrand.address, href: academyBrand.addressHref },
  ];
  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto max-w-7xl px-5 py-16 lg:px-8 lg:py-24">
        <div className="grid gap-12 lg:grid-cols-[.82fr_1.18fr] lg:items-start">
          <div className="lg:sticky lg:top-36">
            <p className="eyebrow">Contact Amaris</p>
            <h1 className="section-title mt-4">How can we help you move forward?</h1>
            <p className="mt-6 max-w-xl text-lg leading-8 text-[#60708a]">Ask about a mathematics course, registration, payments or your student account. Give us enough detail to direct your enquiry to the right support.</p>
            <div className="mt-9 grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
              {contactCards.map(({ Icon, label, value, href }) => {
                const content = <><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-[#eaf1fb] text-[#1f5bbd]"><Icon className="size-5" /></span><span><span className="block text-sm font-semibold text-[#60708a]">{label}</span><span className="mt-1 block break-words text-base font-semibold text-[#0a1b36]">{value}</span></span></>;
                return href ? <a key={label} href={href} target={href.startsWith("http") ? "_blank" : undefined} rel={href.startsWith("http") ? "noreferrer" : undefined} className="flex items-start gap-4 rounded-2xl border border-[#dce4ef] bg-white p-4 transition hover:-translate-y-0.5 hover:border-[#b9c9df] hover:shadow-md">{content}</a> : <div key={label} className="flex items-start gap-4 rounded-2xl border border-[#dce4ef] bg-white p-4">{content}</div>;
              })}
            </div>
          </div>
          <div className="relative overflow-hidden rounded-[2rem] bg-white p-6 shadow-[0_22px_70px_rgba(9,35,75,.12)] ring-1 ring-[#dce4ef] sm:p-9">
            <div className="absolute right-0 top-0 h-2 w-36 bg-[#ffcc66]" />
            <p className="text-xs font-bold uppercase tracking-[.18em] text-[#1f5bbd]">Enquiry form</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-[-.035em] text-[#0a1b36]">Send us a message</h2>
            <p className="mt-3 text-base leading-7 text-[#60708a]">Required fields are marked with an asterisk. We will use your details only to respond to this enquiry.</p>
            <EnquiryForm />
          </div>
        </div>
      </section>
      <section className="bg-[#0b2a5b] px-5 py-16 text-white lg:px-8">
        <div className="mx-auto max-w-7xl">
          <p className="text-xs font-bold uppercase tracking-[.18em] text-[#ffcc66]">Help us respond faster</p>
          <div className="mt-5 grid gap-8 md:grid-cols-3">
            {[["Course guidance", "Include your curriculum, level and the mathematics topics you want to strengthen."], ["Payment support", "Include your order reference, but never send card details, passwords or one-time PINs."], ["Technical help", "Tell us which device you used, what you expected and what happened instead."]].map(([title, copy]) => <div key={title}><h2 className="text-xl font-semibold">{title}</h2><p className="mt-3 text-base leading-7 text-white/65">{copy}</p></div>)}
          </div>
        </div>
      </section>
      <Footer />
    </main>
  );
}
