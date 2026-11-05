import Image from "next/image";
import { academyBrand } from "@/lib/brand";

export function BrandLetterhead({ documentLabel }: { documentLabel?: string }) {
  return (
    <header className="letterhead-header">
      <div className="letterhead-accent" />
      <div className="flex items-start justify-between gap-6 px-8 pb-5 pt-7 sm:px-10">
        <div className="flex min-w-0 items-center gap-4">
          <div className="grid size-20 shrink-0 place-items-center rounded-2xl bg-white p-1.5 shadow-[0_8px_24px_rgba(7,21,45,.12)] ring-1 ring-[#dce4ef]">
            <Image src={academyBrand.logoPath} alt={`${academyBrand.name} logo`} width={80} height={80} unoptimized className="size-full object-contain" />
          </div>
          <div>
            <p className="text-xl font-bold tracking-[-.025em] text-[#07152d] sm:text-2xl">{academyBrand.name}</p>
            <p className="mt-1 text-xs font-bold uppercase tracking-[.16em] text-[#1f5bbd]">Mathematics · Learning · Progress</p>
            <p className="mt-2 text-sm text-[#60708a]">Managing Director: {academyBrand.managingDirector}</p>
          </div>
        </div>
        {documentLabel && <span className="hidden rounded-full bg-[#edf3ff] px-4 py-2 text-xs font-bold uppercase tracking-[.14em] text-[#1f5bbd] sm:block">{documentLabel}</span>}
      </div>
      <div className="grid gap-2 border-y border-[#dce4ef] bg-[#f6f8fc] px-8 py-3 text-[11px] leading-5 text-[#43526a] sm:grid-cols-2 sm:px-10 lg:grid-cols-4">
        <a href={academyBrand.phoneHref}><span className="font-bold text-[#0b2a5b]">Cell:</span> {academyBrand.phoneDisplay}</a>
        <a href={academyBrand.emailHref} className="break-all"><span className="font-bold text-[#0b2a5b]">Email:</span> {academyBrand.email}</a>
        <a href={academyBrand.addressHref} target="_blank" rel="noreferrer"><span className="font-bold text-[#0b2a5b]">Address:</span> {academyBrand.address}</a>
        <a href={academyBrand.websiteHref}><span className="font-bold text-[#0b2a5b]">Web:</span> {academyBrand.website}</a>
      </div>
    </header>
  );
}

export function BrandDocumentFooter({ reference }: { reference?: string }) {
  return (
    <footer className="letterhead-footer mt-auto border-t-2 border-[#ffcc66] px-8 py-4 text-[10px] leading-5 text-[#60708a] sm:px-10">
      <div className="flex flex-col justify-between gap-1 sm:flex-row">
        <span>{academyBrand.name} · {academyBrand.address}</span>
        {reference && <span className="font-semibold text-[#0b2a5b]">Reference: {reference}</span>}
      </div>
      <div className="mt-1 flex flex-col justify-between gap-1 sm:flex-row">
        <span>{academyBrand.phoneDisplay} · {academyBrand.email}</span>
        <span>Professional mathematics education and learner support</span>
      </div>
    </footer>
  );
}
