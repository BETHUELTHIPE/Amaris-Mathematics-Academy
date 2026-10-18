"use client";

import { useRef, useState } from "react";
import { Check, Copy, Share2 } from "lucide-react";

type ShareWebsiteButtonProps = {
  compact?: boolean;
};

const SHARE_TITLE = "Amaris Mathematics Academy";
const SHARE_MESSAGE =
  "Explore Amaris Mathematics Academy for CAPS, IEB, TVET and university learning support.";

function publicHomepageUrl(): string {
  // Share the public home page only: never expose a student dashboard URL,
  // a payment reference, a login token, or any private query parameters.
  return new URL("/", window.location.origin).toString();
}

export function ShareWebsiteButton({ compact = false }: ShareWebsiteButtonProps) {
  const [status, setStatus] = useState<"idle" | "copied" | "manual">("idle");
  const [manualUrl, setManualUrl] = useState("");
  const manualInput = useRef<HTMLInputElement>(null);

  async function shareWebsite() {
    const url = publicHomepageUrl();
    setStatus("idle");

    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ title: SHARE_TITLE, text: SHARE_MESSAGE, url });
        return;
      } catch (error) {
        // Cancelling the operating system share sheet is not a failure.
        if (error instanceof DOMException && error.name === "AbortError") return;
        // Browsers can reject Web Share even when the API is present.
      }
    }

    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(url);
      setStatus("copied");
    } catch {
      // Permission-restricted browsers still have a usable manual copy path.
      setManualUrl(url);
      setStatus("manual");
      window.requestAnimationFrame(() => {
        manualInput.current?.focus();
        manualInput.current?.select();
      });
    }
  }

  const label = status === "copied" ? "Link copied!" : "Share website";

  return (
    <span className={compact ? "relative inline-flex shrink-0 flex-col" : "relative inline-flex flex-col items-start"}>
      <button
        type="button"
        aria-label={label}
        onClick={shareWebsite}
        className={
          compact
            ? "inline-flex min-h-9 items-center justify-center gap-1.5 rounded-full border border-white/20 px-2.5 text-xs font-semibold text-white transition hover:border-[#ffcc66] hover:text-[#ffcc66] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ffcc66] sm:px-3"
            : "inline-flex min-h-11 items-center gap-2 rounded-full border border-[#ffcc66]/60 px-4 py-2 text-sm font-semibold text-[#ffcc66] transition hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ffcc66]"
        }
      >
        {status === "copied" ? <Check className="size-4" aria-hidden="true" /> : <Share2 className="size-4" aria-hidden="true" />}
        <span className={compact ? "hidden sm:inline" : ""}>{label}</span>
      </button>
      <span role="status" aria-live="polite" className={compact ? "sr-only" : "mt-2 text-xs text-white/75"}>
        {status === "copied" ? "Amaris website link copied to clipboard." : status === "manual" ? "Select and copy the website link below." : ""}
      </span>
      {status === "manual" && (
        <div className={compact ? "absolute right-0 top-full z-[80] mt-2 w-56 rounded-lg border border-white/20 bg-[#07152d] p-3 shadow-xl" : "mt-2 w-full max-w-xs rounded-lg border border-white/20 bg-[#07152d] p-3"}>
          <label htmlFor={compact ? "amaris-share-header-url" : "amaris-share-footer-url"} className="mb-2 block text-xs text-white">
            Copy this public website link
          </label>
          <div className="flex items-center gap-2">
            <input
              ref={manualInput}
              id={compact ? "amaris-share-header-url" : "amaris-share-footer-url"}
              readOnly
              value={manualUrl}
              onFocus={(event) => event.currentTarget.select()}
              className="min-w-0 flex-1 rounded border border-white/30 bg-white px-2 py-2 text-xs text-[#07152d]"
            />
            <Copy aria-hidden="true" className="size-4 shrink-0 text-[#ffcc66]" />
          </div>
        </div>
      )}
    </span>
  );
}
