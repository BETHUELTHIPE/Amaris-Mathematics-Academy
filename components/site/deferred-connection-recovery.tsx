"use client";

import { lazy, Suspense, useEffect, useState } from "react";

const LazyConnectionRecovery = lazy(() =>
  import("@/components/site/connection-recovery").then((module) => ({
    default: module.ConnectionRecovery,
  })),
);

export function DeferredConnectionRecovery() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const activateRecovery = () => setReady(true);
    const protectOfflineSubmission = (event: SubmitEvent) => {
      if (navigator.onLine) return;
      event.preventDefault();
      setReady(true);
    };

    if (!navigator.onLine) setReady(true);
    window.addEventListener("offline", activateRecovery, { once: true });
    document.addEventListener("submit", protectOfflineSubmission, true);

    return () => {
      window.removeEventListener("offline", activateRecovery);
      document.removeEventListener("submit", protectOfflineSubmission, true);
    };
  }, []);

  if (!ready) return null;

  return (
    <Suspense fallback={null}>
      <LazyConnectionRecovery />
    </Suspense>
  );
}
