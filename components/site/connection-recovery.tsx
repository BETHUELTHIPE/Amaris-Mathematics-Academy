"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, PlugZap, RefreshCw, X } from "lucide-react";

export function ConnectionRecovery() {
  const [offline, setOffline] = useState(() => typeof navigator !== "undefined" && !navigator.onLine);
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
      restorationTimer = window.setTimeout(() => setRestored(false), 4500);
    };

    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);
    return () => {
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
      if (restorationTimer) window.clearTimeout(restorationTimer);
    };
  }, []);

  if (dismissed || (!offline && !restored)) return null;

  return (
    <div className="fixed inset-x-4 bottom-4 z-[100] mx-auto max-w-2xl rounded-2xl border border-white/15 bg-[#07152d] p-4 text-white shadow-[0_24px_80px_rgba(7,21,45,.35)] sm:p-5" role="status" aria-live="polite">
      <div className="flex items-start gap-3">
        <span className={`grid size-10 shrink-0 place-items-center rounded-xl ${offline ? "bg-[#ffcc66]/15 text-[#ffcc66]" : "bg-[#daf5ec] text-[#147a4b]"}`}>{offline ? <PlugZap className="size-5" /> : <CheckCircle2 className="size-5" />}</span>
        <div className="min-w-0 flex-1">
          <p className="font-bold">{offline ? "Connection lost" : "Connection restored"}</p>
          <p className="mt-1 text-sm leading-6 text-white/65">{offline ? "Keep this page open. Safe form fields remain in this tab where possible, and nothing will be submitted until you reconnect." : "You can continue where you left off."}</p>
          {offline && <div className="mt-3 flex flex-wrap items-center gap-4 text-sm"><button type="button" onClick={() => navigator.onLine ? window.location.reload() : setOffline(true)} className="inline-flex items-center gap-2 font-bold text-[#ffcc66]"><RefreshCw className="size-4" />Try again</button><Link href="/connection-lost" className="font-semibold text-white/70 hover:text-white">Recovery help</Link></div>}
        </div>
        <button type="button" onClick={() => setDismissed(true)} className="rounded-lg p-1 text-white/50 hover:bg-white/10 hover:text-white" aria-label="Dismiss connection message"><X className="size-4" /></button>
      </div>
    </div>
  );
}
