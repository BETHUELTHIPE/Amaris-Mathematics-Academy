"use client";

import { lazy, Suspense, useEffect, useState } from "react";

const LazyConnectionRecovery = lazy(() =>
  import("@/components/site/connection-recovery").then((module) => ({
    default: module.ConnectionRecovery,
  })),
);

type IdleWindow = Window & {
  requestIdleCallback?: (
    callback: () => void,
    options?: { timeout: number },
  ) => number;
  cancelIdleCallback?: (handle: number) => void;
};

export function DeferredConnectionRecovery() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const idleWindow = window as IdleWindow;

    if (idleWindow.requestIdleCallback) {
      const handle = idleWindow.requestIdleCallback(() => setReady(true), {
        timeout: 1500,
      });
      return () => idleWindow.cancelIdleCallback?.(handle);
    }

    const handle = window.setTimeout(() => setReady(true), 250);
    return () => window.clearTimeout(handle);
  }, []);

  if (!ready) return null;

  return (
    <Suspense fallback={null}>
      <LazyConnectionRecovery />
    </Suspense>
  );
}
