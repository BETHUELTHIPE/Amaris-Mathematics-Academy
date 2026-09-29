"use client";

import { useState, type ComponentType } from "react";

type AssistantComponent = ComponentType<{ initialOpen?: boolean }>;

export function AmarisAssistantLauncher() {
  const [Assistant, setAssistant] = useState<AssistantComponent | null>(null);
  const [loading, setLoading] = useState(false);

  async function openAssistant() {
    if (Assistant || loading) return;

    setLoading(true);
    try {
      const module = await import("@/components/site/amaris-assistant");
      setAssistant(() => module.AmarisAssistant);
    } finally {
      setLoading(false);
    }
  }

  if (Assistant) {
    return <Assistant initialOpen />;
  }

  return (
    <div className="fixed bottom-5 right-5 z-50 sm:bottom-7 sm:right-7">
      <button
        type="button"
        onClick={openAssistant}
        disabled={loading}
        aria-busy={loading}
        aria-label="Open Amaris Assistant"
        className="inline-flex items-center gap-2 rounded-full bg-[#07152d] px-5 py-3.5 font-semibold text-white shadow-[0_16px_45px_rgba(7,21,45,.3)] transition hover:-translate-y-0.5 hover:bg-[#0b2a5b] disabled:cursor-wait disabled:opacity-80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ffcc66]"
      >
        <span
          aria-hidden="true"
          className="grid size-7 place-items-center rounded-full bg-[#ffcc66] text-base font-bold text-[#07152d]"
        >
          ✦
        </span>
        {loading ? "Opening…" : "Amaris Assistant"}
      </button>
    </div>
  );
}
