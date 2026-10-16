import Link from "next/link";
import { ArrowLeft, X } from "lucide-react";

/** Visible, keyboard-accessible exit for standalone forms. Does not submit data. */
export function FormCloseLink({ href = "/" }: { href?: string }) {
  return (
    <Link
      href={href}
      aria-label="Close form"
      className="inline-flex min-h-11 items-center justify-center gap-2 rounded-full border border-[#cbd5e1] bg-white px-4 py-2 text-sm font-semibold text-[#0b2a5b] transition hover:bg-[#edf3ff] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]"
    >
      <X className="size-4" aria-hidden="true" />
      Close
    </Link>
  );
}

/** Explicit in-site return destination; avoids unreliable browser history or a form submit. */
export function FormBackLink({ href, label = "Back" }: { href: string; label?: string }) {
  return (
    <Link
      href={href}
      aria-label={label}
      className="inline-flex min-h-11 items-center justify-center gap-2 rounded-full border border-[#cbd5e1] bg-white px-4 py-2 text-sm font-semibold text-[#0b2a5b] transition hover:bg-[#edf3ff] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]"
    >
      <ArrowLeft className="size-4" aria-hidden="true" />
      {label}
    </Link>
  );
}
