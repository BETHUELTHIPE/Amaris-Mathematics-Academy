import Link from "next/link";
import { signOutAction } from "@/app/auth/actions";
import { getStudentIdentity } from "@/lib/auth";

type NavigationLink = {
  label: string;
  url: string;
  open_in_new_tab: boolean;
};

export async function AuthControls({ links }: { links: NavigationLink[] }) {
  const student = await getStudentIdentity();
  const authenticated = Boolean(student);
  const verified = student?.emailVerified === true;
  const primaryHref = verified ? "/dashboard" : authenticated ? "/verify-email" : "/register";
  const primaryLabel = verified ? "My dashboard" : authenticated ? "Verify email" : "Register";

  return (
    <>
      <div className="hidden min-w-[13rem] items-center justify-end gap-3 lg:flex">
        {authenticated ? (
          <>
            {verified && <Link href="/documents" className="text-sm font-semibold text-white/70 hover:text-white">Documents</Link>}
            <Link href={primaryHref} className="rounded-full border border-white/20 px-4 py-2 text-sm font-semibold hover:bg-white/10">{primaryLabel}</Link>
            <form action={signOutAction}><button type="submit" className="text-sm text-white/65 hover:text-white">Sign out</button></form>
          </>
        ) : (
          <>
            <Link href="/login" className="text-sm font-semibold text-white/80 hover:text-white">Log in</Link>
            <Link href="/register" className="rounded-full bg-[#ffcc66] px-5 py-2.5 text-sm font-bold text-[#07152d] transition hover:bg-[#ffd780]">Register</Link>
          </>
        )}
      </div>

      <details className="relative lg:hidden">
        <summary className="cursor-pointer list-none rounded-lg border border-white/20 px-3 py-2 text-sm">Menu</summary>
        <div className="absolute right-0 mt-3 w-64 rounded-2xl border border-white/10 bg-[#0c2042] p-3 shadow-2xl">
          {links.map(({ label, url, open_in_new_tab }) => <Link key={url} href={url} target={open_in_new_tab ? "_blank" : undefined} rel={open_in_new_tab ? "noreferrer" : undefined} className="block rounded-xl px-3 py-2.5 text-sm text-white/80 hover:bg-white/10">{label}</Link>)}
          {verified && <Link href="/documents" className="block rounded-xl px-3 py-2.5 text-sm text-white/80 hover:bg-white/10">Documents & invoices</Link>}
          <Link href={primaryHref} className="mt-2 block rounded-xl bg-[#ffcc66] px-3 py-2.5 text-center text-sm font-bold text-[#07152d]">{primaryLabel}</Link>
          {authenticated ? <form action={signOutAction}><button type="submit" className="mt-2 w-full rounded-xl px-3 py-2.5 text-left text-sm text-white/70 hover:bg-white/10">Sign out</button></form> : <Link href="/login" className="mt-2 block rounded-xl px-3 py-2.5 text-center text-sm text-white/80 hover:bg-white/10">Log in</Link>}
        </div>
      </details>
    </>
  );
}
