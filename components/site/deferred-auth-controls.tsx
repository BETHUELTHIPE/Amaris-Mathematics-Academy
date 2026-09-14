"use client";

import { lazy, Suspense, useEffect, useState } from "react";

type NavigationLink = {
  label: string;
  url: string;
  open_in_new_tab: boolean;
};

type AuthResult = { authenticated?: boolean };

const LazyAuthControls = lazy(() =>
  import("@/components/site/auth-controls").then((module) => ({
    default: module.AuthControls,
  })),
);

function AnonymousAuthControls({ links, checking = false }: { links: NavigationLink[]; checking?: boolean }) {
  return (
    <>
      <div
        className="hidden min-w-[13rem] items-center justify-end gap-3 sm:flex"
        aria-busy={checking}
      >
        <a href="/login" className="text-sm font-semibold text-white/80 hover:text-white">
          Log in
        </a>
        <a
          href="/register"
          className="rounded-full bg-[#ffcc66] px-5 py-2.5 text-sm font-bold text-[#07152d] transition hover:bg-[#ffd780]"
        >
          Register
        </a>
      </div>

      <details className="relative sm:hidden">
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
          <a
            href="/register"
            className="mt-2 block rounded-xl bg-[#ffcc66] px-3 py-2.5 text-center text-sm font-bold text-[#07152d]"
          >
            Register
          </a>
          <a
            href="/login"
            className="mt-2 block rounded-xl px-3 py-2.5 text-center text-sm text-white/80 hover:bg-white/10"
          >
            Log in
          </a>
        </div>
      </details>
    </>
  );
}

export function DeferredAuthControls({ links }: { links: NavigationLink[] }) {
  const [authenticated, setAuthenticated] = useState(false);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    let timeoutHandle: number | undefined;

    const checkAuth = () => {
      fetch("/api/auth-state", {
        cache: "no-store",
        credentials: "same-origin",
        signal: controller.signal,
      })
        .then(async (response): Promise<AuthResult | null> =>
          response.ok ? ((await response.json()) as AuthResult) : null,
        )
        .then((result) => setAuthenticated(result?.authenticated === true))
        .catch(() => undefined)
        .finally(() => {
          if (!controller.signal.aborted) setChecking(false);
        });
    };

    const scheduleCheck = () => {
      timeoutHandle = window.setTimeout(checkAuth, 400);
    };

    if (document.readyState === "complete") scheduleCheck();
    else window.addEventListener("load", scheduleCheck, { once: true });

    return () => {
      controller.abort();
      window.removeEventListener("load", scheduleCheck);
      if (timeoutHandle !== undefined) window.clearTimeout(timeoutHandle);
    };
  }, []);

  if (!authenticated) return <AnonymousAuthControls links={links} checking={checking} />;

  return (
    <Suspense fallback={<AnonymousAuthControls links={links} />}>
      <LazyAuthControls links={links} />
    </Suspense>
  );
}
