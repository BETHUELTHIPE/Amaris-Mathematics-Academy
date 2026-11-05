"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Copy, ExternalLink, Share2 } from "lucide-react";
import {
  MATRIC_UPGRADES_SHARE_MESSAGE,
  MATRIC_UPGRADES_SHARE_TITLE,
  MATRIC_UPGRADES_WHATSAPP_URL,
  PUBLIC_MATRIC_UPGRADES_URL,
} from "@/lib/matric-upgrades-sharing";

type ShareStatus = "idle" | "copied" | "manual";

export function ShareMatricUpgrades() {
  const [status, setStatus] = useState<ShareStatus>("idle");
  const urlInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (status === "manual") {
      urlInput.current?.focus();
      urlInput.current?.select();
    }
  }, [status]);

  async function copyLink() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(PUBLIC_MATRIC_UPGRADES_URL);
      setStatus("copied");
    } catch {
      setStatus("manual");
    }
  }

  async function sharePage() {
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({
          title: MATRIC_UPGRADES_SHARE_TITLE,
          text: MATRIC_UPGRADES_SHARE_MESSAGE,
          url: PUBLIC_MATRIC_UPGRADES_URL,
        });
        setStatus("idle");
        return;
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        // Restricted share sheets fall back to copying the public link.
      }
    }
    await copyLink();
  }

  return (
    <div className="mt-7 rounded-2xl border border-[#b9c8dd] bg-white p-5 shadow-sm sm:p-7">
      <label htmlFor="amaris-matric-share-url" className="mb-2 block text-sm font-semibold text-[#07152d]">
        Public Matric Upgrades link
      </label>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          ref={urlInput}
          id="amaris-matric-share-url"
          type="url"
          aria-label="Public link to Amaris Matric Upgrades"
          readOnly
          value={PUBLIC_MATRIC_UPGRADES_URL}
          onFocus={(event) => event.currentTarget.select()}
          className="min-h-12 min-w-0 flex-1 rounded-xl border border-[#b9c8dd] bg-[#f5f7fb] px-3 py-2 text-sm text-[#173d72] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]"
        />
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={copyLink}
            className="inline-flex min-h-12 items-center gap-2 rounded-xl bg-[#1f5bbd] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#164994] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]"
          >
            {status === "copied" ? <Check className="size-4" aria-hidden="true" /> : <Copy className="size-4" aria-hidden="true" />}
            {status === "copied" ? "Copied!" : "Copy link"}
          </button>
          <button
            type="button"
            onClick={sharePage}
            className="inline-flex min-h-12 items-center gap-2 rounded-xl border border-[#1f5bbd] px-4 py-2 text-sm font-semibold text-[#1f5bbd] transition hover:bg-[#eaf1fb] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]"
          >
            <Share2 className="size-4" aria-hidden="true" /> Share page
          </button>
          <a
            href={MATRIC_UPGRADES_WHATSAPP_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-12 items-center gap-2 rounded-xl border border-[#b9c8dd] px-4 py-2 text-sm font-semibold text-[#173d72] transition hover:bg-[#eaf1fb] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]"
          >
            WhatsApp <ExternalLink className="size-4" aria-hidden="true" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        </div>
      </div>
      <p role="status" aria-live="polite" className="mt-3 min-h-5 text-sm text-[#526781]">
        {status === "copied"
          ? "Matric Upgrades link copied. You can paste it into a message."
          : status === "manual"
            ? "Select the link above and copy it using your keyboard."
            : "Share this page with friends, colleagues or someone planning to improve their matric marks."}
      </p>
    </div>
  );
}
