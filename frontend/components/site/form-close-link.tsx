import Link from "next/link";
import { X } from "lucide-react";

/** Close a form without submitting it. The destination is always an internal route. */
export function FormCloseLink({ href = "/" }: { href?: string }) {
  return (
    <Link
      href={href}
      aria-label="Close form without submitting"
      className="inline-flex min-h-11 items-center justify-center gap-2 rounded-full border border-[#cbd5e1] bg-white px-5 py-2 text-sm font-semibold text-[#0b2a5b] transition hover:bg-[#edf3ff] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]"
    >
      <X className="size-4" aria-hidden="true" /> Close
    </Link>
  );
}
