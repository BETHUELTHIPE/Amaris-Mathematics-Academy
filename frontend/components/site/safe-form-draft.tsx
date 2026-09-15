"use client";

import { useEffect, useRef } from "react";

type DraftPayload = {
  version: 1;
  expiresAt: number;
  values: Record<string, string>;
};

const SENSITIVE_NAME = /(password|passcode|otp|token|secret|card|cvv|cvc|bank|payment|signature|passphrase|upload|file)/i;
const EXCLUDED_TYPES = new Set(["password", "hidden", "file", "checkbox", "radio"]);
const DRAFT_LIFETIME_MS = 2 * 60 * 60 * 1000;

export function SafeFormDraft({ draftKey, allowedFields }: { draftKey: string; allowedFields: string[] }) {
  const markerRef = useRef<HTMLSpanElement>(null);
  const storageKey = `amaris:safe-draft:${draftKey}`;

  useEffect(() => {
    const form = markerRef.current?.closest("form");
    if (!form) return;

    const safeNames = allowedFields.filter((name) => name && !SENSITIVE_NAME.test(name));

    function getControl(name: string) {
      const control = form?.elements.namedItem(name);
      if (control instanceof HTMLInputElement && !EXCLUDED_TYPES.has(control.type)) return control;
      if (control instanceof HTMLTextAreaElement || control instanceof HTMLSelectElement) return control;
      return null;
    }

    try {
      const stored = sessionStorage.getItem(storageKey);
      if (stored) {
        const payload = JSON.parse(stored) as DraftPayload;
        if (payload.version === 1 && payload.expiresAt > Date.now()) {
          safeNames.forEach((name) => {
            const control = getControl(name);
            const value = payload.values[name];
            if (control && typeof value === "string" && !control.value) {
              control.value = value;
              control.dispatchEvent(new Event("input", { bubbles: true }));
              control.dispatchEvent(new Event("change", { bubbles: true }));
            }
          });
        } else {
          sessionStorage.removeItem(storageKey);
        }
      }
    } catch {
      sessionStorage.removeItem(storageKey);
    }

    let timer: number | undefined;
    const save = () => {
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const values: Record<string, string> = {};
        safeNames.forEach((name) => {
          const control = getControl(name);
          if (control) values[name] = control.value.slice(0, 2500);
        });
        const payload: DraftPayload = { version: 1, expiresAt: Date.now() + DRAFT_LIFETIME_MS, values };
        sessionStorage.setItem(storageKey, JSON.stringify(payload));
      }, 180);
    };

    form.addEventListener("input", save);
    form.addEventListener("change", save);
    window.addEventListener("offline", save);
    return () => {
      form.removeEventListener("input", save);
      form.removeEventListener("change", save);
      window.removeEventListener("offline", save);
      if (timer) window.clearTimeout(timer);
    };
  }, [allowedFields, storageKey]);

  return <span ref={markerRef} hidden aria-hidden="true" />;
}

export function ClearSafeFormDraft({ draftKey }: { draftKey: string }) {
  useEffect(() => {
    sessionStorage.removeItem(`amaris:safe-draft:${draftKey}`);
  }, [draftKey]);
  return null;
}

