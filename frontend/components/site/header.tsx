import Link from "next/link";
import { Mail, MapPin, Phone } from "lucide-react";
import { AuthControls } from "@/components/site/auth-controls";
import { getManagedBrand, getManagedNavigation } from "@/lib/cms";

export async function Header() {
  const [academyBrand, links] = await Promise.all([
    getManagedBrand(),
    getManagedNavigation("header"),
  ]);
  return (
    <header className="sticky top-0 z-50 border-b border-white/10 bg-[#07152d]/95 text-white backdrop-blur-xl">
      <div className="border-b border-white/10 bg-[#041026]">
        <div className="mx-auto flex h-9 max-w-7xl items-center justify-between gap-4 px-5 text-xs text-white/70 lg:px-8">
          <div className="flex min-w-0 items-center gap-4 sm:gap-6">
            <a href={academyBrand.phoneHref} className="flex shrink-0 items-center gap-2 transition hover:text-white"><Phone className="size-3.5 text-[#ffcc66]" />{academyBrand.phoneDisplay}</a>
            <a href={academyBrand.emailHref} className="flex min-w-0 items-center gap-2 transition hover:text-white"><Mail className="size-3.5 shrink-0 text-[#ffcc66]" /><span className="hidden truncate sm:inline">{academyBrand.email}</span><span className="sm:hidden">Email us</span></a>
          </div>
          <a href={academyBrand.addressHref} target="_blank" rel="noreferrer" className="hidden items-center gap-2 transition hover:text-white md:flex"><MapPin className="size-3.5 text-[#ffcc66]" />{academyBrand.addressShort}</a>
        </div>
      </div>
      <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-5 lg:px-8">
        <Link href="/" className="relative z-10 flex shrink-0 items-center gap-3 font-semibold tracking-tight" aria-label="Amaris Mathematics Academy home">
          <span
            aria-hidden="true"
            className="size-12 shrink-0 rounded-xl bg-white bg-contain bg-center bg-no-repeat p-1 shadow-[0_8px_22px_rgba(0,0,0,.22)] ring-1 ring-[#ffcc66]/70 sm:size-14"
            style={{ backgroundImage: `url(${academyBrand.logoPath})` }}
          />
          <span className="leading-tight">Amaris <span className="hidden text-white/60 sm:inline">Mathematics Academy</span></span>
        </Link>
        <nav className="hidden items-center gap-6 text-sm text-white/75 lg:flex" aria-label="Main navigation">
          {links.map(({ label, url, open_in_new_tab }) => <Link key={url} href={url} target={open_in_new_tab ? "_blank" : undefined} rel={open_in_new_tab ? "noreferrer" : undefined} className="transition hover:text-white">{label}</Link>)}
        </nav>
        <AuthControls links={links} />
      </div>
    </header>
  );
}
