"use client";

import Image from "next/image";
import Link from "next/link";
import { AlertTriangle, BookOpenCheck, CreditCard, LockKeyhole, PlugZap, ShieldAlert, TimerReset, Wrench } from "lucide-react";
import { academyBrand } from "@/lib/brand";
import type { RecoveryDefinition, RecoveryKind } from "@/lib/recovery";
import { CorrelationReference, RecoveryActionLink } from "@/components/site/recovery-actions";

const iconByKind: Record<RecoveryKind, typeof AlertTriangle> = {
  request: AlertTriangle,
  permission: ShieldAlert,
  missing: BookOpenCheck,
  "rate-limit": TimerReset,
  server: Wrench,
  maintenance: Wrench,
  payment: CreditCard,
  session: LockKeyhole,
  connection: PlugZap,
};

export function RecoveryScreen({ definition, reference }: { definition: RecoveryDefinition; reference?: string }) {
  const Icon = iconByKind[definition.kind];

  return (
    <main className="relative flex min-h-screen flex-col overflow-hidden bg-[#07152d] text-white">
      <div className="graph-paper pointer-events-none absolute inset-0 opacity-35" />
      <div className="pointer-events-none absolute -right-32 top-20 size-[34rem] rounded-full bg-[#1f5bbd]/25 blur-3xl" />
      <header className="relative z-10 border-b border-white/10">
        <div className="mx-auto flex h-24 max-w-7xl items-center justify-between px-5 lg:px-8">
          <Link href="/" className="flex items-center gap-3 font-semibold" aria-label="Amaris Mathematics Academy home">
            <span className="grid size-12 place-items-center rounded-xl bg-white p-1 ring-1 ring-[#ffcc66]/70">
              <Image src={academyBrand.logoPath} alt="" width={48} height={48} priority unoptimized className="size-full object-contain" />
            </span>
            <span>Amaris <span className="hidden text-white/55 sm:inline">Mathematics Academy</span></span>
          </Link>
          <Link href="/contact" className="rounded-full border border-white/20 px-4 py-2 text-sm font-semibold text-white/85 hover:bg-white/10">Contact support</Link>
        </div>
      </header>

      <section className="relative z-10 mx-auto grid w-full max-w-7xl flex-1 items-center gap-12 px-5 py-14 lg:grid-cols-[1fr_.72fr] lg:px-8 lg:py-20">
        <div className="max-w-3xl">
          <div className="flex items-center gap-4">
            <span className="grid size-14 place-items-center rounded-2xl border border-[#ffcc66]/30 bg-[#ffcc66]/10 text-[#ffcc66]"><Icon className="size-7" /></span>
            {definition.code && <span className="font-mono text-5xl font-semibold tracking-[-.06em] text-white/20 sm:text-7xl">{definition.code}</span>}
          </div>
          <p className="mt-8 text-xs font-extrabold uppercase tracking-[.2em] text-[#ffcc66]">{definition.eyebrow}</p>
          <h1 className="mt-4 max-w-3xl text-4xl font-semibold tracking-[-.05em] sm:text-6xl">{definition.title}</h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-white/70">{definition.message}</p>
          {definition.reassurance && <p className="mt-4 max-w-2xl text-sm leading-7 text-white/52">{definition.reassurance}</p>}
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <RecoveryActionLink action={definition.primaryAction} primary />
            {definition.secondaryAction && <RecoveryActionLink action={definition.secondaryAction} />}
          </div>
          <CorrelationReference value={reference} />
        </div>

        <aside className="rounded-[2rem] border border-white/12 bg-white/[.07] p-7 shadow-2xl backdrop-blur sm:p-9">
          <p className="text-xs font-extrabold uppercase tracking-[.18em] text-[#ffcc66]">Safe next steps</p>
          <ol className="mt-6 grid gap-5 text-sm leading-6 text-white/70">
            <li className="flex gap-4"><span className="grid size-7 shrink-0 place-items-center rounded-full bg-white/10 font-bold text-white">1</span><span>Use the main action once and allow the page time to respond.</span></li>
            <li className="flex gap-4"><span className="grid size-7 shrink-0 place-items-center rounded-full bg-white/10 font-bold text-white">2</span><span>For payment issues, check your order before starting another payment.</span></li>
            <li className="flex gap-4"><span className="grid size-7 shrink-0 place-items-center rounded-full bg-white/10 font-bold text-white">3</span><span>Share only the support reference below—never your password, OTP, or card details.</span></li>
          </ol>
          {definition.showSupport && <div className="mt-8 border-t border-white/10 pt-6"><p className="text-sm font-semibold text-white">Need help?</p><div className="mt-3 grid gap-2 text-sm text-white/65"><a className="hover:text-[#ffcc66]" href={academyBrand.phoneHref}>{academyBrand.phoneDisplay}</a><a className="break-all hover:text-[#ffcc66]" href={academyBrand.emailHref}>{academyBrand.email}</a></div></div>}
        </aside>
      </section>

      <footer className="relative z-10 border-t border-white/10 px-5 py-5 text-center text-xs text-white/40">
        © {new Date().getFullYear()} {academyBrand.name}. Your privacy and security matter.
      </footer>
    </main>
  );
}
