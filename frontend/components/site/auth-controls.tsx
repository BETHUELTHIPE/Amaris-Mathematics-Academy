"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { signOutAction } from "@/app/auth/actions";

type NavigationLink = {
  label: string;
  url: string;
  open_in_new_tab: boolean;
};

type AuthState = "loading" | "anonymous" | "unverified" | "verified";
type AuthResult = { authenticated?: boolean; emailVerified?: boolean };
type IdleWindow = Window & {
  requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number;
  cancelIdleCallback?: (handle: number) => void;
};

export function AuthControls({ links }: { links: NavigationLink[] }) {
  const [state, setState] = useState<AuthState>("loading");

  useEffect(() => {
    const controller = new AbortController();
    const idleWindow = window as IdleWindow;
    let idleHandle: number | undefined;
    let timeoutHandle: number | undefined;

    const loadAuthState = () => {
      fetch("/api/auth-state", {
        cache: "no-store",
        credentials: "same-origin",
        signal: controller.signal,
      })
        .then(async (response): Promise<AuthResult | null> =>
          response.ok ? ((await response.json()) as AuthResult) : null,
        )
        .then((result) => {
          if (!result?.authenticated) setState("anonymous");
          else setState(result.emailVerified ? "verified" : "unverified");
        })
        .catch(() => {
          if (!controller.signal.aborted) setState("anonymous");
        });
    };

    if (idleWindow.requestIdleCallback) {
      idleHandle = idleWindow.requestIdleCallback(loadAuthState, { timeout: 750 });
    } else {
      timeoutHandle = window.setTimeout(loadAuthState, 150);
    }

    return () => {
      controller.abort();
      if (idleHandle !== undefined) idleWindow.cancelIdleCallback?.(idleHandle);
      if (timeoutHandle !== undefined) window.clearTimeout(timeoutHandle);
    };
  }, []);

  const authenticated = state === "verified" || state === "unverified";
  const primaryHref = state === "verified" ? "/dashboard" : state === "unverified" ? "/verify-email" : "/register";
  const primaryLabel = state === "verified" ? "My dashboard" : state === "unverified" ? "Verify email" : "Register";

  return (
    <>
      <div className="hidden min-w-[13rem] items-center justify-end gap-3 lg:flex" aria-busy={state === "loading"}>
        {authenticated ? (
          <>
            {state === "verified" && <Link href="/documents" className="text-sm font-semibold text-white/70 hover:text-white">Documents</Link>}
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
          {state === "verified" && <Link href="/documents" className="block rounded-xl px-3 py-2.5 text-sm text-white/80 hover:bg-white/10">Documents & invoices</Link>}
          <Link href={primaryHref} className="mt-2 block rounded-xl bg-[#ffcc66] px-3 py-2.5 text-center text-sm font-bold text-[#07152d]">{primaryLabel}</Link>
          {authenticated ? <form action={signOutAction}><button type="submit" className="mt-2 w-full rounded-xl px-3 py-2.5 text-left text-sm text-white/70 hover:bg-white/10">Sign out</button></form> : <Link href="/login" className="mt-2 block rounded-xl px-3 py-2.5 text-center text-sm text-white/80 hover:bg-white/10">Log in</Link>}
        </div>
      </details>
    </>
  );
}
