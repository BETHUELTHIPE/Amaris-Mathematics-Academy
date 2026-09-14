"use client";

import { lazy, Suspense, useEffect, useState } from "react";

type NavigationLink = {
  label: string;
  url: string;
  open_in_new_tab: boolean;
};

type IdleWindow = Window & {
  requestIdleCallback?: (
    callback: () => void,
    options?: { timeout: number },
  ) => number;
  cancelIdleCallback?: (handle: number) => void;
};

const LazyAuthControls = lazy(() =>
  import("@/components/site/auth-controls").then((module) => ({
    default: module.AuthControls,
  })),
);

function AuthControlsPlaceholder() {
  return (
    <>
      <div className="hidden min-w-[13rem] sm:block" aria-hidden="true" />
      <div
        className="h-10 w-[4.25rem] rounded-lg border border-white/20 sm:hidden"
        aria-hidden="true"
      />
    </>
  );
}

export function DeferredAuthControls({ links }: { links: NavigationLink[] }) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const idleWindow = window as IdleWindow;

    if (idleWindow.requestIdleCallback) {
      const handle = idleWindow.requestIdleCallback(() => setReady(true), {
        timeout: 700,
      });
      return () => idleWindow.cancelIdleCallback?.(handle);
    }

    const handle = window.setTimeout(() => setReady(true), 120);
    return () => window.clearTimeout(handle);
  }, []);

  if (!ready) return <AuthControlsPlaceholder />;

  return (
    <Suspense fallback={<AuthControlsPlaceholder />}>
      <LazyAuthControls links={links} />
    </Suspense>
  );
}
