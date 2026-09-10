import Link from "next/link";
import Image from "next/image";
import { Mail, MapPin, Phone } from "lucide-react";
import { signOutAction } from "@/app/auth/actions";
import { getStudentIdentity } from "@/lib/auth";
import { getManagedBrand, getManagedNavigation } from "@/lib/cms";

export async function Header() {
  const [user, academyBrand, links] = await Promise.all([
    getStudentIdentity(),
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
          <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-white p-1 shadow-[0_8px_22px_rgba(0,0,0,.22)] ring-1 ring-[#ffcc66]/70 sm:size-14">
            <Image src={academyBrand.logoPath} alt="" width={56} height={56} priority unoptimized className="size-full object-contain" />
          </span>
          <span className="leading-tight">Amaris <span className="hidden text-white/60 sm:inline">Mathematics Academy</span></span>
        </Link>
        <nav className="hidden items-center gap-6 text-sm text-white/75 lg:flex" aria-label="Main navigation">
          {links.map(({ label, url, open_in_new_tab }) => <Link key={url} href={url} target={open_in_new_tab ? "_blank" : undefined} rel={open_in_new_tab ? "noreferrer" : undefined} className="transition hover:text-white">{label}</Link>)}
        </nav>
        <div className="hidden items-center gap-3 sm:flex">
          {user ? (
            <>
              <Link href="/dashboard" className="rounded-full border border-white/20 px-4 py-2 text-sm font-semibold hover:bg-white/10">My dashboard</Link>
              <Link href="/documents" className="text-sm font-semibold text-white/70 hover:text-white">Documents</Link>
              <form action={signOutAction}><button type="submit" className="text-sm text-white/65 hover:text-white">Sign out</button></form>
            </>
          ) : (
            <>
              <Link href="/login" className="text-sm font-semibold text-white/80 hover:text-white">Log in</Link>
              <Link href="/register" className="rounded-full bg-[#ffcc66] px-5 py-2.5 text-sm font-bold text-[#07152d] transition hover:bg-[#ffd780]">Register</Link>
            </>
          )}
        </div>
        <details className="relative sm:hidden">
          <summary className="cursor-pointer list-none rounded-lg border border-white/20 px-3 py-2 text-sm">Menu</summary>
          <div className="absolute right-0 mt-3 w-64 rounded-2xl border border-white/10 bg-[#0c2042] p-3 shadow-2xl">
            {links.map(({ label, url, open_in_new_tab }) => <Link key={url} href={url} target={open_in_new_tab ? "_blank" : undefined} rel={open_in_new_tab ? "noreferrer" : undefined} className="block rounded-xl px-3 py-2.5 text-sm text-white/80 hover:bg-white/10">{label}</Link>)}
            {user && <Link href="/documents" className="block rounded-xl px-3 py-2.5 text-sm text-white/80 hover:bg-white/10">Documents & invoices</Link>}
            <Link href={user ? "/dashboard" : "/register"} className="mt-2 block rounded-xl bg-[#ffcc66] px-3 py-2.5 text-center text-sm font-bold text-[#07152d]">{user ? "My dashboard" : "Register"}</Link>
            {user ? <form action={signOutAction}><button type="submit" className="mt-2 w-full rounded-xl px-3 py-2.5 text-left text-sm text-white/70 hover:bg-white/10">Sign out</button></form> : <Link href="/login" className="mt-2 block rounded-xl px-3 py-2.5 text-center text-sm text-white/80 hover:bg-white/10">Log in</Link>}
          </div>
        </details>
      </div>
    </header>
  );
}
