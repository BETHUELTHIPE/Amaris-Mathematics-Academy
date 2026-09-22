"use client";

import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { ArrowLeft, Bot, MessageCircle, Mic, Send, Sparkles, Volume2, X } from "lucide-react";

type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
};

type AssistantMode = "chat" | "voice";

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: ArrayLike<{
    0: { transcript: string };
    isFinal: boolean;
  }>;
};

type SpeechRecognitionErrorEventLike = {
  error?: string;
};

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

const welcome: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text: "Hello. I’m Amaris Assistant. Ask me about courses, registration, pricing, payments, or information published on the Amaris Mathematics Academy website.",
};

function getSpeechRecognition(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;

  const browserWindow = window as typeof window & {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };

  return browserWindow.SpeechRecognition ?? browserWindow.webkitSpeechRecognition ?? null;
}

export function AmarisAssistant() {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<AssistantMode | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([welcome]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [voiceSupported, setVoiceSupported] = useState(true);
  const [voiceError, setVoiceError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  useEffect(() => {
    setVoiceSupported(Boolean(getSpeechRecognition()) && "speechSynthesis" in window);

    return () => {
      recognitionRef.current?.stop();
      window.speechSynthesis?.cancel();
    };
  }, []);

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages, open, busy]);

  function speak(text: string) {
    if (mode !== "voice" || typeof window === "undefined" || !("speechSynthesis" in window)) {
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-ZA";
    utterance.rate = 0.98;
    window.speechSynthesis.speak(utterance);
  }

  async function sendMessage(messageOverride?: string) {
    const message = (messageOverride ?? draft).trim();
    if (!message || busy) return;

    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", text: message },
    ]);
    setDraft("");
    setBusy(true);
    setVoiceError("");

    let reply = "Amaris Assistant is temporarily unavailable. Please try again shortly.";

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
      reply =
        response.ok && payload.answer
          ? payload.answer
          : payload.detail || reply;
    } catch {
      // Use the safe fallback response below.
    } finally {
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: "assistant", text: reply },
      ]);
      setBusy(false);
      speak(reply);
    }
  }

  function startVoiceQuestion() {
    if (busy || listening) return;

    const SpeechRecognition = getSpeechRecognition();
    if (!SpeechRecognition) {
      setVoiceSupported(false);
      setVoiceError("Voice mode is not supported by this browser. Please choose chat mode.");
      return;
    }

    setVoiceError("");
    const recognition = new SpeechRecognition();
    recognition.lang = "en-ZA";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onstart = () => setListening(true);
    recognition.onend = () => setListening(false);
    recognition.onerror = (event) => {
      setListening(false);
      setVoiceError(
        event.error === "not-allowed"
          ? "Microphone permission was denied. Allow microphone access or choose chat mode."
          : "I could not hear that clearly. Please try the microphone again or choose chat mode.",
      );
    };
    recognition.onresult = (event) => {
      let transcript = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        if (event.results[index]?.isFinal) {
          transcript += event.results[index]?.[0]?.transcript ?? "";
        }
      }

      const question = transcript.trim();
      if (!question) {
        setVoiceError("I could not hear a question. Please try again.");
        return;
      }

      setDraft(question);
      void sendMessage(question);
    };

    recognitionRef.current = recognition;

    try {
      recognition.start();
    } catch {
      setListening(false);
      setVoiceError("The microphone could not start. Please try again or choose chat mode.");
    }
  }

  function chooseMode(nextMode: AssistantMode) {
    window.speechSynthesis?.cancel();
    recognitionRef.current?.stop();
    setListening(false);
    setVoiceError("");
    setMode(nextMode);
  }

  function resetMode() {
    window.speechSynthesis?.cancel();
    recognitionRef.current?.stop();
    setListening(false);
    setVoiceError("");
    setMode(null);
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

          {mode === null ? (
            <div className="flex flex-1 flex-col justify-center bg-[#f5f7fb] p-5">
              <div className="mx-auto max-w-sm text-center">
                <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]">
                  <Sparkles className="size-6" aria-hidden="true" />
                </span>
                <h2 className="mt-4 text-xl font-semibold text-[#0a1b36]">How would you like to use Amaris Assistant?</h2>
                <p className="mt-2 text-sm leading-6 text-[#60708a]">
                  Choose chat to type your questions, or voice to speak and hear the answer.
                </p>
              </div>

              <div className="mt-6 grid gap-3" role="group" aria-label="Choose assistant mode">
                <button
                  type="button"
                  onClick={() => chooseMode("chat")}
                  className="flex items-center gap-4 rounded-2xl border border-[#cdd8e7] bg-white p-4 text-left transition hover:border-[#1f5bbd] hover:bg-[#f8fbff] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]"
                >
                  <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-[#edf3ff] text-[#1f5bbd]">
                    <MessageCircle className="size-5" aria-hidden="true" />
                  </span>
                  <span>
                    <span className="block font-semibold text-[#0a1b36]">Chat assistant</span>
                    <span className="mt-1 block text-sm text-[#60708a]">Type your question and read the response.</span>
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => chooseMode("voice")}
                  className="flex items-center gap-4 rounded-2xl border border-[#cdd8e7] bg-white p-4 text-left transition hover:border-[#1f5bbd] hover:bg-[#f8fbff] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]"
                >
                  <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-[#fff4d8] text-[#8a5a00]">
                    <Mic className="size-5" aria-hidden="true" />
                  </span>
                  <span>
                    <span className="block font-semibold text-[#0a1b36]">Voice assistant</span>
                    <span className="mt-1 block text-sm text-[#60708a]">Speak your question and hear the GPT response.</span>
                  </span>
                </button>
              </div>

              {!voiceSupported ? (
                <p className="mt-4 text-center text-xs leading-5 text-[#8a5a00]">
                  Voice mode depends on browser microphone and speech support. Chat mode remains available.
                </p>
              ) : null}
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between border-b border-[#dce4ef] bg-white px-4 py-2.5">
                <button
                  type="button"
                  onClick={resetMode}
                  className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-semibold text-[#1f5bbd] hover:bg-[#edf3ff] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]"
                >
                  <ArrowLeft className="size-3.5" aria-hidden="true" />
                  Change mode
                </button>
                <span className="text-xs font-semibold text-[#60708a]">
                  {mode === "voice" ? "Voice assistant" : "Chat assistant"}
                </span>
              </div>

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

              {mode === "chat" ? (
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
              ) : (
                <div className="border-t border-[#dce4ef] bg-white p-4">
                  <div className="flex flex-col items-center text-center">
                    <button
                      type="button"
                      onClick={startVoiceQuestion}
                      disabled={busy || listening}
                      aria-label={listening ? "Listening for your question" : "Start voice question"}
                      className="grid size-14 place-items-center rounded-full bg-[#ffcc66] text-[#07152d] shadow-sm transition hover:bg-[#ffd780] disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]"
                    >
                      {busy ? (
                        <Volume2 className="size-6" aria-hidden="true" />
                      ) : (
                        <Mic className="size-6" aria-hidden="true" />
                      )}
                    </button>
                    <p className="mt-2 text-sm font-semibold text-[#0a1b36]">
                      {busy
                        ? "Preparing the website-based answer…"
                        : listening
                          ? "Listening…"
                          : "Tap the microphone and ask your question"}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-[#60708a]">
                      Your spoken question is transcribed in the browser, sent to Amaris Assistant, and the GPT answer is read aloud.
                    </p>
                    {voiceError ? (
                      <p role="alert" className="mt-2 text-xs leading-5 text-[#9a3412]">
                        {voiceError}
                      </p>
                    ) : null}
                  </div>
                  <p className="mt-3 text-center text-[11px] leading-4 text-[#6b7b90]">
                    Do not speak passwords, card details, OTPs, or other secrets.
                  </p>
                </div>
              )}
            </>
          )}
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
