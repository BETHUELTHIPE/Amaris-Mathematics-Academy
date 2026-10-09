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

    // Defer the initial offline check to avoid a synchronous state update
    // during effect setup while retaining immediate offline recovery.
    const initialOfflineCheck = window.setTimeout(() => {
      if (!navigator.onLine) activateRecovery();
    }, 0);
    window.addEventListener("offline", activateRecovery, { once: true });
    document.addEventListener("submit", protectOfflineSubmission, true);

    return () => {
      window.clearTimeout(initialOfflineCheck);
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
