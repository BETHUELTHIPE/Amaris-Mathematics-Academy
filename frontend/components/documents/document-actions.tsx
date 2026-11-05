"use client";

import { Download, Printer } from "lucide-react";
import { Button } from "@/components/ui/button";

export function DocumentActions() {
  const printDocument = () => window.print();

  return (
    <div className="print-hidden flex flex-wrap gap-3">
      <Button onClick={printDocument} className="rounded-full bg-[#0b2a5b] px-5 text-white hover:bg-[#163d78]"><Printer className="size-4" /> Print document</Button>
      <Button onClick={printDocument} variant="outline" className="rounded-full border-[#b8c7da] px-5 text-[#0b2a5b]"><Download className="size-4" /> Save as PDF</Button>
    </div>
  );
}
