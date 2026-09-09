import Link from "next/link";
import Image from "next/image";
import { Clock3, Mail, MapPin, Phone } from "lucide-react";
import { academyBrand } from "@/lib/brand";

export function Footer() {
  return (
    <footer className="border-t border-white/10 bg-[#061126] text-white">
      <div className="mx-auto grid max-w-7xl gap-10 px-5 py-14 sm:grid-cols-2 lg:grid-cols-[1.35fr_.7fr_1.15fr] lg:px-8">
        <div className="max-w-md">
          <div className="flex items-center gap-3 font-semibold">
            <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-white p-1">
              <Image src={academyBrand.logoPath} alt={`${academyBrand.name} logo`} width={44} height={44} unoptimized className="size-full object-contain" />
            </span>
            <span>{academyBrand.name}</span>
          </div>
          <p className="mt-5 text-sm leading-7 text-white/58">Structured mathematics courses for South African school, TVET and university students. Learn clearly, practise deliberately and track real progress.</p>
        </div>
        <div>
          <p className="text-sm font-semibold text-[#ffcc66]">Explore</p>
          <div className="mt-4 grid gap-3 text-sm text-white/65">
            <Link href="/courses">Mathematics courses</Link><Link href="/how-it-works">How it works</Link><Link href="/pricing">Pricing</Link><Link href="/about">About us</Link><Link href="/documents">Documents & invoices</Link>
          </div>
        </div>
        <div>
          <p className="text-sm font-semibold text-[#ffcc66]">Contact & support</p>
          <div className="mt-4 grid gap-4 text-sm text-white/65">
            <a href={academyBrand.phoneHref} className="flex items-start gap-3 transition hover:text-white"><Phone className="mt-0.5 size-4 shrink-0 text-[#ffcc66]" /><span>{academyBrand.phoneDisplay}</span></a>
            <a href={academyBrand.emailHref} className="flex min-w-0 items-start gap-3 transition hover:text-white"><Mail className="mt-0.5 size-4 shrink-0 text-[#ffcc66]" /><span className="break-all">{academyBrand.email}</span></a>
            <a href={academyBrand.addressHref} target="_blank" rel="noreferrer" className="flex items-start gap-3 transition hover:text-white"><MapPin className="mt-0.5 size-4 shrink-0 text-[#ffcc66]" /><span>{academyBrand.address}</span></a>
            <span className="flex items-start gap-3"><Clock3 className="mt-0.5 size-4 shrink-0 text-[#ffcc66]" /><span>{academyBrand.hours}</span></span>
            <Link href="/contact" className="mt-1 inline-flex w-fit rounded-full border border-white/20 px-4 py-2 font-semibold text-white transition hover:bg-white/10">Send an enquiry</Link>
          </div>
        </div>
      </div>
      <div className="border-t border-white/10 px-5 py-5 text-xs text-white/45"><div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-3 sm:flex-row"><span>© {new Date().getFullYear()} Amaris Mathematics Academy. Mathematics, taught with clarity.</span><span className="flex gap-5"><Link href="/terms" className="hover:text-white">Student terms</Link><Link href="/privacy" className="hover:text-white">Privacy</Link></span></div></div>
    </footer>
  );
}
