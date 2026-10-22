"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw } from "lucide-react";

export function StudentWorkflowRefresh() {
  const router = useRouter();
  const [updating, startTransition] = useTransition();

  return <button
    type="button"
    disabled={updating}
    onClick={() => startTransition(() => router.refresh())}
    className="inline-flex min-h-11 items-center justify-center gap-2 rounded-full border border-[#bfd0e8] px-4 text-sm font-bold text-[#194f95] transition hover:bg-[#edf3ff] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd] disabled:opacity-60"
    aria-label="Refresh my workflow progress"
  >
    <RefreshCw aria-hidden="true" className={"size-4 " + (updating ? "animate-spin" : "")} />
    {updating ? "Checking progress" : "Refresh progress"}
  </button>;
}
