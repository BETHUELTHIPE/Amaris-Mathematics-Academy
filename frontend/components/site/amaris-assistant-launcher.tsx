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
      const assistantModule = await import("./amaris-assistant");
      setAssistant(() => assistantModule.AmarisAssistant);
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
        onClick={() => void openAssistant()}
        disabled={loading}
        aria-haspopup="dialog"
        aria-controls="amaris-assistant-panel"
        className="inline-flex min-h-12 items-center gap-2 rounded-full bg-[#07152d] px-5 py-3 text-sm font-semibold text-white shadow-[0_18px_55px_rgba(7,21,45,.24)] transition hover:bg-[#0b2a5b] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd] disabled:cursor-wait disabled:opacity-80"
      >
        <span aria-hidden="true" className="size-2 rounded-full bg-[#ffcc66]" />
        {loading ? "Opening Amaris Assistant…" : "Amaris Assistant"}
      </button>
    </div>
  );
}
