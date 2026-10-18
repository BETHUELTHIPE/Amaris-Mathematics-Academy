/* Public sharing UI is intentionally server-rendered.
 * A tiny optional script enhances these buttons without React hydration.
 * The default button and its accessible name remain visible without JS.
 */
import { Copy, Share2 } from "lucide-react";

export function ShareWebsiteButton({ compact = false }: { compact?: boolean }) {
  const inputId = compact ? "amaris-share-header-url" : "amaris-share-footer-url";
  return (
    <span
      data-share-website
      className={compact ? "relative inline-flex shrink-0 flex-col" : "relative inline-flex flex-col items-start"}
    >
      <button
        type="button"
        data-share-trigger
        aria-label="Share website"
        className={
          compact
            ? "inline-flex min-h-9 items-center justify-center gap-1.5 rounded-full border border-white/20 px-2.5 text-xs font-semibold text-white transition hover:border-[#ffcc66] hover:text-[#ffcc66] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ffcc66] sm:px-3"
            : "inline-flex min-h-11 items-center gap-2 rounded-full border border-[#ffcc66]/60 px-4 py-2 text-sm font-semibold text-[#ffcc66] transition hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ffcc66]"
        }
      >
        <Share2 className="size-4" aria-hidden="true" />
        <span data-share-label className={compact ? "hidden sm:inline" : ""}>Share website</span>
      </button>
      <span
        role="status"
        aria-live="polite"
        data-share-status
        className={compact ? "sr-only" : "mt-2 text-xs text-white/75"}
      />
      <span
        data-share-manual
        hidden
        className={compact
          ? "absolute right-0 top-full z-[80] mt-2 w-56 rounded-lg border border-white/20 bg-[#07152d] p-3 shadow-xl"
          : "mt-2 w-full max-w-xs rounded-lg border border-white/20 bg-[#07152d] p-3"}
      >
        <label htmlFor={inputId} className="mb-2 block text-xs text-white">
          Copy this public website link
        </label>
        <span className="flex items-center gap-2">
          <input
            data-share-url
            id={inputId}
            type="text"
            readOnly
            defaultValue=""
            className="min-w-0 flex-1 rounded border border-white/30 bg-white px-2 py-2 text-xs text-[#07152d]"
          />
          <Copy aria-hidden="true" className="size-4 shrink-0 text-[#ffcc66]" />
        </span>
      </span>
      {/* Safe to include in both header/footer; enhancer installs a single listener. */}
      <script src="/share-website-enhance.js" defer />
    </span>
  );
}
