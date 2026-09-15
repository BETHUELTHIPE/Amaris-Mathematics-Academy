"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckCircle2, PlugZap, RefreshCw, X } from "lucide-react";

export function ConnectionRecovery() {
  const [offline, setOffline] = useState(false);
  const [restored, setRestored] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let restorationTimer: number | undefined;

    const handleOffline = () => {
      setOffline(true);
      setRestored(false);
      setDismissed(false);
    };
    const handleOnline = () => {
      setOffline(false);
      setRestored(true);
      setDismissed(false);
      if (restorationTimer) window.clearTimeout(restorationTimer);
      restorationTimer = window.setTimeout(() => setRestored(false), 4500);
    };
    const preventOfflineSubmission = (event: SubmitEvent) => {
      if (navigator.onLine) return;
      event.preventDefault();
      handleOffline();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDismissed(true);
    };

    if (!navigator.onLine) handleOffline();
    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);
    window.addEventListener("keydown", handleKeyDown);
    document.addEventListener("submit", preventOfflineSubmission, true);

    return () => {
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("submit", preventOfflineSubmission, true);
      if (restorationTimer) window.clearTimeout(restorationTimer);
    };
  }, []);

  if (dismissed || (!offline && !restored)) return null;

  return (
    <div
      className="fixed inset-x-4 bottom-4 z-[100] mx-auto max-w-2xl rounded-2xl border border-white/15 bg-[#07152d] p-4 text-white shadow-[0_24px_80px_rgba(7,21,45,.35)] sm:p-5"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <div className="flex items-start gap-3">
        <span
          className={`grid size-10 shrink-0 place-items-center rounded-xl ${offline ? "bg-[#ffcc66]/15 text-[#ffcc66]" : "bg-[#daf5ec] text-[#147a4b]"}`}
        >
          {offline ? <PlugZap className="size-5" /> : <CheckCircle2 className="size-5" />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-bold">{offline ? "Connection lost" : "Connection restored"}</p>
          <p className="mt-1 text-sm leading-6 text-white/65">
            {offline
              ? "Keep this page open. Safe form fields remain in this tab where possible, and nothing will be submitted until you reconnect."
              : "You can continue where you left off."}
          </p>
          {offline && (
            <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
              <button
                type="button"
                onClick={() => {
                  if (navigator.onLine) window.location.reload();
                  else setDismissed(false);
                }}
                className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg font-bold text-[#ffcc66] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#ffcc66]"
              >
                <RefreshCw className="size-4" />
                Try again
              </button>
              <Link
                href="/connection-lost"
                className="inline-flex min-h-11 items-center rounded-lg font-semibold text-white/70 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"
              >
                Recovery help
              </Link>
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="inline-flex min-h-11 cursor-pointer items-center gap-1.5 rounded-lg px-2 text-sm font-semibold text-white/65 hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          aria-label="Close connection notice"
          title="Close connection notice"
        >
          <X className="size-4" aria-hidden="true" />
          <span className="hidden sm:inline">Close</span>
        </button>
      </div>
    </div>
  );
}
