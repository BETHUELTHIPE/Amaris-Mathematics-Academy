/* eslint-disable @next/next/no-html-link-for-pages -- public header auth controls intentionally use full-page anchors to avoid public-route prefetch work */
"use client";

import { useEffect, useState } from "react";
import { signOutAction } from "@/app/auth/actions";

type NavigationLink = {
  label: string;
  url: string;
  open_in_new_tab: boolean;
};

type AuthState = "anonymous" | "unverified" | "verified";

export function AuthControls({ links }: { links: NavigationLink[] }) {
  const [state, setState] = useState<AuthState>("anonymous");

  useEffect(() => {
    let cancelled = false;

    const loadAuthState = async () => {
      try {
        const response = await fetch("/api/auth-state", {
          method: "GET",
          credentials: "same-origin",
          cache: "no-store",
          headers: { Accept: "application/json" },
        });

        if (!response.ok) return;

        const data = (await response.json()) as {
          authenticated?: boolean;
          emailVerified?: boolean;
        };

        if (cancelled) return;
        setState(
          data.authenticated
            ? data.emailVerified
              ? "verified"
              : "unverified"
            : "anonymous",
        );
      } catch {
        // Public pages must remain usable if the auth provider is unavailable.
        // Protected routes continue to enforce authentication server-side.
      }
    };

    const schedule = () => void loadAuthState();
    const idleWindow = window as Window & {
      requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number;
      cancelIdleCallback?: (id: number) => void;
    };

    let idleId: number | undefined;
    let timeoutId: number | undefined;

    if (idleWindow.requestIdleCallback) {
      idleId = idleWindow.requestIdleCallback(schedule, { timeout: 1200 });
    } else {
      timeoutId = window.setTimeout(schedule, 0);
    }

    return () => {
      cancelled = true;
      if (idleId !== undefined) idleWindow.cancelIdleCallback?.(idleId);
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
  }, []);

  const authenticated = state !== "anonymous";
  const primaryHref =
    state === "verified"
      ? "/dashboard"
      : state === "unverified"
        ? "/verify-email"
        : "/register";
  const primaryLabel =
    state === "verified"
      ? "My dashboard"
      : state === "unverified"
        ? "Verify email"
        : "Register";

  return (
    <>
      <div className="hidden min-w-[13rem] items-center justify-end gap-3 lg:flex">
        {authenticated ? (
          <>
            {state === "verified" && (
              <a href="/documents" className="text-sm font-semibold text-white/70 hover:text-white">
                Documents
              </a>
            )}
            <a
              href={primaryHref}
              className="rounded-full border border-white/20 px-4 py-2 text-sm font-semibold hover:bg-white/10"
            >
              {primaryLabel}
            </a>
            <form action={signOutAction}>
              <button type="submit" className="text-sm text-white/65 hover:text-white">
                Sign out
              </button>
            </form>
          </>
        ) : (
          <>
            <a href="/login" className="text-sm font-semibold text-white/80 hover:text-white">
              Log in
            </a>
            <a
              href="/register"
              className="rounded-full bg-[#ffcc66] px-5 py-2.5 text-sm font-bold text-[#07152d] transition hover:bg-[#ffd780]"
            >
              Register
            </a>
          </>
        )}
      </div>

      <details className="relative lg:hidden">
        <summary className="cursor-pointer list-none rounded-lg border border-white/20 px-3 py-2 text-sm">
          Menu
        </summary>
        <div className="absolute right-0 mt-3 w-64 rounded-2xl border border-white/10 bg-[#0c2042] p-3 shadow-2xl">
          {links.map(({ label, url, open_in_new_tab }) => (
            <a
              key={url}
              href={url}
              target={open_in_new_tab ? "_blank" : undefined}
              rel={open_in_new_tab ? "noreferrer" : undefined}
              className="block rounded-xl px-3 py-2.5 text-sm text-white/80 hover:bg-white/10"
            >
              {label}
            </a>
          ))}
          {state === "verified" && (
            <a
              href="/documents"
              className="block rounded-xl px-3 py-2.5 text-sm text-white/80 hover:bg-white/10"
            >
              Documents & invoices
            </a>
          )}
          <a
            href={primaryHref}
            className="mt-2 block rounded-xl bg-[#ffcc66] px-3 py-2.5 text-center text-sm font-bold text-[#07152d]"
          >
            {primaryLabel}
          </a>
          {authenticated ? (
            <form action={signOutAction}>
              <button
                type="submit"
                className="mt-2 w-full rounded-xl px-3 py-2.5 text-left text-sm text-white/70 hover:bg-white/10"
              >
                Sign out
              </button>
            </form>
          ) : (
            <a
              href="/login"
              className="mt-2 block rounded-xl px-3 py-2.5 text-center text-sm text-white/80 hover:bg-white/10"
            >
              Log in
            </a>
          )}
        </div>
      </details>
    </>
  );
}
