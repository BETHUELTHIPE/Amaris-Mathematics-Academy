"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Bot, Send, Sparkles, X } from "lucide-react";

type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
};

const welcome: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text: "Hello. I’m Amaris Assistant. Ask me about courses, registration, pricing, payments, or information published on the Amaris Mathematics Academy website.",
};

export function AmarisAssistant() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([welcome]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages, open, busy]);

  async function sendMessage() {
    const message = draft.trim();
    if (!message || busy) return;

    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", text: message },
    ]);
    setDraft("");
    setBusy(true);

    try {
      const response = await fetch("/api/assistant/", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ message }),
      });
      const payload = (await response.json().catch(() => ({}))) as {
        answer?: string;
        detail?: string;
      };
      const reply =
        response.ok && payload.answer
          ? payload.answer
          : payload.detail || "Amaris Assistant is temporarily unavailable. Please try again shortly.";

      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: "assistant", text: reply },
      ]);
    } catch {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: "Amaris Assistant is temporarily unavailable. Please try again shortly.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendMessage();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  }

  return (
    <div className="fixed bottom-5 right-5 z-50 sm:bottom-7 sm:right-7">
      {open ? (
        <section
          id="amaris-assistant-panel"
          role="dialog"
          aria-label="Amaris Assistant"
          className="mb-3 flex h-[min(640px,78vh)] w-[min(390px,calc(100vw-2rem))] flex-col overflow-hidden rounded-[1.75rem] border border-[#dce4ef] bg-white shadow-[0_28px_90px_rgba(7,21,45,.22)]"
        >
          <header className="flex items-center justify-between bg-[#07152d] px-5 py-4 text-white">
            <div className="flex items-center gap-3">
              <span className="grid size-10 place-items-center rounded-2xl bg-[#ffcc66] text-[#07152d]">
                <Bot className="size-5" aria-hidden="true" />
              </span>
              <div>
                <p className="font-semibold">Amaris Assistant</p>
                <p className="text-xs text-white/65">Answers from website information only</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="grid size-9 place-items-center rounded-full text-white/75 transition hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ffcc66]"
              aria-label="Close Amaris Assistant"
            >
              <X className="size-5" />
            </button>
          </header>

          <div
            className="flex-1 space-y-3 overflow-y-auto bg-[#f5f7fb] p-4"
            aria-live="polite"
            aria-relevant="additions"
          >
            {messages.map((message) => (
              <div
                key={message.id}
                className={message.role === "user" ? "flex justify-end" : "flex justify-start"}
              >
                <div
                  className={
                    message.role === "user"
                      ? "max-w-[85%] rounded-2xl rounded-br-md bg-[#0b2a5b] px-4 py-3 text-sm leading-6 text-white"
                      : "max-w-[88%] rounded-2xl rounded-bl-md border border-[#dce4ef] bg-white px-4 py-3 text-sm leading-6 text-[#0a1b36]"
                  }
                >
                  {message.text}
                </div>
              </div>
            ))}
            {busy ? (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-bl-md border border-[#dce4ef] bg-white px-4 py-3 text-sm text-[#60708a]">
                  Amaris Assistant is checking the website…
                </div>
              </div>
            ) : null}
            <div ref={endRef} />
          </div>

          <form onSubmit={onSubmit} className="border-t border-[#dce4ef] bg-white p-4">
            <label htmlFor="amaris-assistant-question" className="sr-only">
              Ask Amaris Assistant
            </label>
            <div className="flex items-end gap-2 rounded-2xl border border-[#cdd8e7] bg-white p-2 focus-within:border-[#1f5bbd] focus-within:ring-2 focus-within:ring-[#1f5bbd]/15">
              <textarea
                id="amaris-assistant-question"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={onKeyDown}
                maxLength={1200}
                rows={2}
                disabled={busy}
                placeholder="Ask about Amaris…"
                className="min-h-12 flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-5 text-[#0a1b36] outline-none placeholder:text-[#8a98aa]"
              />
              <button
                type="submit"
                disabled={busy || !draft.trim()}
                className="grid size-11 shrink-0 place-items-center rounded-xl bg-[#ffcc66] text-[#07152d] transition hover:bg-[#ffd780] disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]"
                aria-label="Send question"
              >
                <Send className="size-4" />
              </button>
            </div>
            <p className="mt-2 text-[11px] leading-4 text-[#6b7b90]">
              Do not send passwords, card details, OTPs, or other secrets.
            </p>
          </form>
        </section>
      ) : null}

      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls="amaris-assistant-panel"
        className="inline-flex items-center gap-2 rounded-full bg-[#07152d] px-5 py-3.5 font-semibold text-white shadow-[0_16px_45px_rgba(7,21,45,.3)] transition hover:-translate-y-0.5 hover:bg-[#0b2a5b] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ffcc66]"
      >
        <span className="grid size-7 place-items-center rounded-full bg-[#ffcc66] text-[#07152d]">
          <Sparkles className="size-4" aria-hidden="true" />
        </span>
        Amaris Assistant
      </button>
    </div>
  );
}
