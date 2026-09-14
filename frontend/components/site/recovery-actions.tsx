"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Check, Copy, RefreshCw } from "lucide-react";
import { createCorrelationReference, type RecoveryAction } from "@/lib/recovery";

export function RecoveryActionLink({ action, primary = false }: { action: RecoveryAction; primary?: boolean }) {
  const router = useRouter();
  const classes = primary
    ? "inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-[#ffcc66] px-6 py-3 text-sm font-bold text-[#07152d] transition hover:bg-[#ffd980]"
    : "inline-flex min-h-12 items-center justify-center gap-2 rounded-full border border-white/20 px-6 py-3 text-sm font-bold text-white transition hover:bg-white/10";

  if (action.retry) {
    return <button type="button" className={classes} onClick={() => window.location.reload()}>{action.label}<RefreshCw className="size-4" /></button>;
  }

  if (action.href === "back") {
    return <button type="button" className={classes} onClick={() => window.history.length > 1 ? router.back() : router.push("/")}><ArrowLeft className="size-4" />{action.label}</button>;
  }

  return <Link className={classes} href={action.href ?? "/"}>{action.label}</Link>;
}

export function CorrelationReference({ value }: { value?: string }) {
  const [copied, setCopied] = useState(false);
  const [generated] = useState(createCorrelationReference);
  const reference = value ?? generated;

  async function copyReference() {
    try {
      await navigator.clipboard.writeText(reference);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-white/10 pt-5 text-xs text-white/55">
      <span>Support reference</span>
      <code className="rounded-md bg-white/10 px-2 py-1 font-mono text-white/85">{reference}</code>
      <button type="button" onClick={copyReference} className="inline-flex items-center gap-1 rounded-md px-2 py-1 font-semibold text-[#ffcc66] hover:bg-white/10" aria-label="Copy support reference">
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}{copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
