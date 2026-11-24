"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { MESSAGE_MAX_LENGTH, type ChatRole, type Message, type MessagePage } from "@/lib/chat";

const time = new Intl.DateTimeFormat("en-ZA", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Africa/Johannesburg",
});
const senderNames = { student: "Student", tutor: "Tutor", admin: "Academy Admin" };
const POLL_DELAY = 12_000;

async function errorMessage(response: Response): Promise<string> {
  const data = await response.json().catch(() => null) as { detail?: unknown } | null;
  return typeof data?.detail === "string" ? data.detail : "Messages are temporarily unavailable.";
}

export function ChatThread({ room, role, assignment }: { room: string; role: ChatRole; assignment?: string }) {
  const endpoint = `/api/chat/${room}?${assignment ? `assignment=${assignment}&` : ""}`;
  const [messages, setMessages] = useState<Message[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [older, setOlder] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [sendError, setSendError] = useState("");
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const latest = useRef<string | null>(null);
  const refreshRef = useRef<() => void>(() => {});
  const pendingMessage = useRef<{ text: string; client_id: string } | null>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const stickToLatest = useRef(true);
  const composer = useRef<HTMLTextAreaElement>(null);
  const requestOlder = useRef<AbortController | null>(null);
  const requestSend = useRef<AbortController | null>(null);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let running = false;
    let queued = false;
    let accessLost = false;
    const controller = new AbortController();

    async function refresh() {
      if (accessLost || document.hidden || controller.signal.aborted) return;
      if (running) {
        queued = true;
        return;
      }
      clearTimeout(timer);
      running = true;
      try {
        const after = latest.current;
        const response = await fetch(`${endpoint}${after ? `after=${after}` : ""}`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) {
          const error = await errorMessage(response);
          if ([401, 403, 404].includes(response.status)) {
            accessLost = true;
            setBlocked(true);
            setMessages([]);
            setDraft("");
          }
          setFeedback(error);
          return;
        }
        const result = (await response.json()) as MessagePage;
        if (!after) setOlder(result.has_more);
        if (result.messages.length > 0) {
          latest.current = result.messages[result.messages.length - 1].id;
          setMessages((current) => [...current, ...result.messages]);
          queued ||= Boolean(after && result.has_more);
        }
        setLoaded(true);
        setFeedback("");
      } catch {
        if (!controller.signal.aborted) setFeedback("Could not refresh the conversation. Try again shortly.");
      } finally {
        running = false;
        if (!controller.signal.aborted && !accessLost) {
          timer = setTimeout(refresh, queued ? 0 : POLL_DELAY);
          queued = false;
        }
      }
    }

    refreshRef.current = () => { void refresh(); };
    void refresh();
    document.addEventListener("visibilitychange", refreshRef.current);
    return () => {
      document.removeEventListener("visibilitychange", refreshRef.current);
      clearTimeout(timer);
      controller.abort();
      requestOlder.current?.abort();
      requestSend.current?.abort();
    };
  }, [endpoint]);

  useEffect(() => {
    if (transcript.current && stickToLatest.current) {
      transcript.current.scrollTop = transcript.current.scrollHeight;
    }
  }, [messages]);

  async function loadOlder() {
    const first = messages[0]?.id;
    if (!first || loadingOlder) return;
    const controller = new AbortController();
    requestOlder.current = controller;
    setLoadingOlder(true);
    try {
      const response = await fetch(`${endpoint}before=${first}`, { cache: "no-store", signal: controller.signal });
      if (!response.ok) {
        setFeedback(await errorMessage(response));
        refreshRef.current();
        return;
      }
      const result = (await response.json()) as MessagePage;
      stickToLatest.current = false;
      setMessages((current) => [...result.messages, ...current]);
      setOlder(result.has_more);
    } catch {
      if (!controller.signal.aborted) setFeedback("Could not load older messages.");
    } finally {
      if (!controller.signal.aborted) setLoadingOlder(false);
    }
  }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || sending || blocked) return;
    if (pendingMessage.current?.text !== text) {
      pendingMessage.current = { text, client_id: crypto.randomUUID() };
    }
    const controller = new AbortController();
    requestSend.current = controller;
    setSending(true);
    setSendError("");
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pendingMessage.current),
        signal: controller.signal,
      });
      if (!response.ok) {
        setSendError(await errorMessage(response));
        if ([401, 403, 404].includes(response.status)) refreshRef.current();
        return;
      }
      pendingMessage.current = null;
      setDraft("");
      stickToLatest.current = true;
      refreshRef.current();
    } catch {
      if (!controller.signal.aborted) setSendError("Could not confirm delivery. Select Send again to retry.");
    } finally {
      if (!controller.signal.aborted) {
        setSending(false);
        composer.current?.focus();
      }
    }
  }

  return (
    <div className="min-w-0">
      {older && !blocked && (
        <button type="button" onClick={loadOlder} disabled={loadingOlder} className="mb-3 min-h-11 text-sm font-semibold text-[#1f5bbd]">
          {loadingOlder ? "Loading…" : "Load older messages"}
        </button>
      )}
      {feedback && <p role="status" className="mb-3 rounded-xl bg-[#fff4d8] p-3 text-sm text-[#553800]">{feedback}</p>}
      {!blocked && (
        <>
          {messages.length === 0 && (
            <p role="status" className="rounded-xl bg-[#f5f7fb] p-4 text-sm text-[#465d78]">
              {loaded ? "No messages yet." : feedback ? "Waiting to reconnect…" : "Loading conversation…"}
            </p>
          )}
          <div
            ref={transcript}
            role="log"
            aria-label="Conversation messages"
            aria-relevant="additions"
            tabIndex={messages.length ? 0 : undefined}
            onScroll={(event) => {
              const list = event.currentTarget;
              stickToLatest.current = list.scrollHeight - list.scrollTop - list.clientHeight < 50;
            }}
            className="max-h-[28rem] overflow-y-auto rounded-xl"
          >
            <ol className="space-y-3">
              {messages.map((message) => (
                <li key={message.id} className={`w-fit max-w-[95%] rounded-2xl px-4 py-3 ${message.sender === role ? "ml-auto bg-[#eaf2ff]" : "bg-[#f5f7fb]"}`}>
                  <p className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-[#465d78]">
                    <strong>{message.sender === role ? "You" : senderNames[message.sender]}</strong>
                    <time dateTime={message.sent_at}>{time.format(new Date(message.sent_at))}</time>
                  </p>
                  <p className="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-[#07152d] [overflow-wrap:anywhere]">{message.text}</p>
                </li>
              ))}
            </ol>
          </div>
          <form onSubmit={send} className="mt-4 grid gap-2">
            <label htmlFor="chat-message" className="text-sm font-semibold text-[#07152d]">Message</label>
            <textarea
              id="chat-message"
              ref={composer}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              rows={3}
              maxLength={MESSAGE_MAX_LENGTH}
              readOnly={sending}
              required
              className="w-full rounded-xl border border-[#8395ab] p-3 text-base text-[#07152d]"
            />
            {sendError && <p role="alert" className="text-sm text-[#9d2222]">{sendError}</p>}
            <button type="submit" disabled={sending || !draft.trim()} className="min-h-11 w-fit rounded-full bg-[#0b2a5b] px-6 text-sm font-bold text-white disabled:opacity-60">
              {sending ? "Sending…" : "Send message"}
            </button>
          </form>
        </>
      )}
    </div>
  );
}
