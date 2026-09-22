"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Bot, Send, X } from "lucide-react";

type AssistantMessage = {
  role: "assistant" | "user";
  text: string;
};

const welcomeMessage =
  "Hello. I’m Amaris Assistant. Ask me about courses, pricing, registration, payments, lessons, or other information published on this website.";

export function AmarisAssistant() {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<AssistantMessage[]>([
    { role: "assistant", text: welcomeMessage },
  ]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
    }
  }, [open]);

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = question.trim();
    if (!value || loading) return;

    setMessages((current) => [...current, { role: "user", text: value }]);
    setQuestion("");
    setLoading(true);

    try {
      const response = await fetch("/api/assistant", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question: value }),
      });
      const payload = (await response.json()) as {
        answer?: string;
        detail?: string;
      };

      if (!response.ok || !payload.answer) {
        throw new Error(payload.detail || "Assistant response was unavailable.");
      }

      setMessages((current) => [
        ...current,
        { role: "assistant", text: payload.answer as string },
      ]);
    } catch {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text:
            "I’m temporarily unavailable. Please use the Contact page and the Amaris team will assist you.",
        },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="fixed bottom-5 right-5 z-50 inline-flex items-center gap-2 rounded-full bg-[#0b2a5b] px-5 py-3.5 font-semibold text-white shadow-[0_16px_45px_rgba(7,21,45,.28)] transition hover:bg-[#1f5bbd] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[#ffcc66]/70"
        aria-expanded={open}
        aria-controls="amaris-assistant-panel"
        aria-label={open ? "Close Amaris Assistant" : "Open Amaris Assistant"}
      >
        <Bot className="size-5" aria-hidden="true" />
        <span>Amaris Assistant</span>
      </button>

      {open ? (
        <section
          id="amaris-assistant-panel"
          role="dialog"
          aria-labelledby="amaris-assistant-title"
          className="fixed bottom-24 right-4 z-50 flex max-h-[70vh] w-[calc(100vw-2rem)] max-w-md flex-col overflow-hidden rounded-3xl border border-[#dce4ef] bg-white shadow-[0_28px_90px_rgba(7,21,45,.24)]"
        >
          <div className="flex items-start justify-between gap-4 border-b border-[#e7edf5] bg-[#07152d] px-5 py-4 text-white">
            <div>
              <div className="flex items-center gap-2">
                <Bot className="size-5 text-[#ffcc66]" aria-hidden="true" />
                <h2 id="amaris-assistant-title" className="font-semibold">
                  Amaris Assistant
                </h2>
              </div>
              <p className="mt-1 text-xs leading-5 text-white/70">
                I answer only from information published on this website.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-full p-2 text-white/80 transition hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ffcc66]"
              aria-label="Close Amaris Assistant"
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          </div>

          <div
            className="min-h-52 flex-1 space-y-3 overflow-y-auto bg-[#f5f7fb] p-4"
            role="log"
            aria-live="polite"
            aria-relevant="additions text"
            aria-busy={loading}
          >
            {messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={
                  message.role === "assistant"
                    ? "max-w-[88%] rounded-2xl rounded-tl-md bg-white px-4 py-3 text-sm leading-6 text-[#263a57] shadow-sm"
                    : "ml-auto max-w-[88%] rounded-2xl rounded-tr-md bg-[#0b2a5b] px-4 py-3 text-sm leading-6 text-white"
                }
              >
                {message.text}
              </div>
            ))}
            {loading ? (
              <p className="text-sm text-[#60708a]" role="status">
                Amaris Assistant is checking the website information…
              </p>
            ) : null}
          </div>

          <form onSubmit={submitQuestion} className="border-t border-[#e7edf5] bg-white p-4">
            <label htmlFor="amaris-assistant-question" className="sr-only">
              Ask Amaris Assistant a question
            </label>
            <textarea
              ref={inputRef}
              id="amaris-assistant-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              maxLength={800}
              rows={3}
              disabled={loading}
              placeholder="Ask about courses, pricing, registration or learning…"
              className="w-full resize-none rounded-2xl border border-[#cbd6e5] bg-white px-4 py-3 text-sm text-[#0a1b36] outline-none transition placeholder:text-[#7a899f] focus:border-[#1f5bbd] focus:ring-4 focus:ring-[#1f5bbd]/10 disabled:cursor-not-allowed disabled:bg-[#f3f5f8]"
            />
            <div className="mt-3 flex items-center justify-between gap-3">
              <p className="text-xs leading-5 text-[#60708a]">
                Do not share passwords, OTPs, card details or other secrets.
              </p>
              <button
                type="submit"
                disabled={loading || question.trim().length < 2}
                className="inline-flex shrink-0 items-center gap-2 rounded-full bg-[#ffcc66] px-4 py-2 text-sm font-bold text-[#07152d] transition hover:bg-[#ffd780] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Send className="size-4" aria-hidden="true" />
                Send
              </button>
            </div>
          </form>
        </section>
      ) : null}
    </>
  );
}
