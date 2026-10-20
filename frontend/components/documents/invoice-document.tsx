import { BrandDocumentFooter, BrandLetterhead } from "@/components/documents/brand-letterhead";

export type InvoiceLine = { description: string; detail?: string; quantity: number; unitPrice: number };

type InvoiceDocumentProps = {
  invoiceNumber: string;
  issueDate: string;
  studentName: string;
  studentEmail: string;
  lines: InvoiceLine[];
  status?: "Paid" | "Pending" | "Template";
};

const formatMoney = (value: number) => new Intl.NumberFormat("en-ZA", { style: "currency", currency: "ZAR", minimumFractionDigits: 2 }).format(value);

export function InvoiceDocument({ invoiceNumber, issueDate, studentName, studentEmail, lines, status = "Paid" }: InvoiceDocumentProps) {
  const subtotal = lines.reduce((total, line) => total + line.quantity * line.unitPrice, 0);
  return (
    <article className="print-sheet relative flex min-h-[1120px] flex-col overflow-hidden rounded-[1.75rem] bg-white shadow-[0_24px_80px_rgba(7,21,45,.14)] ring-1 ring-[#dce4ef] print:min-h-screen print:rounded-none print:shadow-none print:ring-0">
      {status === "Template" && <div className="absolute right-[-64px] top-16 z-10 rotate-45 bg-[#ffcc66] px-20 py-2 text-xs font-black uppercase tracking-[.18em] text-[#07152d]">Preview · Not issued</div>}
      <BrandLetterhead documentLabel="Invoice" />
      <div className="min-w-0 flex-1 px-4 py-7 sm:px-10 sm:py-9">
        <div className="grid min-w-0 gap-7 border-b border-[#dce4ef] pb-8 sm:grid-cols-2">
          <div><p className="text-xs font-bold uppercase tracking-[.16em] text-[#1f5bbd]">Billed to</p><p className="mt-3 text-lg font-bold text-[#07152d]">{studentName}</p><p className="mt-1 break-all text-sm text-[#60708a]">{studentEmail}</p></div>
          <dl className="grid min-w-0 grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm sm:justify-self-end sm:gap-x-5"><dt className="text-[#60708a]">Invoice number</dt><dd className="min-w-0 break-all text-right font-bold text-[#07152d]">{invoiceNumber}</dd><dt className="text-[#60708a]">Issue date</dt><dd className="text-right font-semibold">{issueDate}</dd><dt className="text-[#60708a]">Currency</dt><dd className="text-right font-semibold">ZAR</dd><dt className="text-[#60708a]">Status</dt><dd className="text-right"><span className="rounded-full bg-[#daf5ec] px-2.5 py-1 text-xs font-bold text-[#13715f]">{status}</span></dd></dl>
        </div>
        <div role="region" aria-label="Invoice line items, scroll horizontally on small screens" tabIndex={0} className="mt-8 max-w-full overflow-x-auto rounded-2xl border border-[#dce4ef] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2767d8]"><table className="min-w-[540px] w-full border-collapse text-left text-sm"><thead className="bg-[#07152d] text-white"><tr><th className="px-5 py-4 font-semibold">Description</th><th className="px-4 py-4 text-center font-semibold">Qty</th><th className="px-4 py-4 text-right font-semibold">Unit price</th><th className="px-5 py-4 text-right font-semibold">Amount</th></tr></thead><tbody className="divide-y divide-[#e3e9f1]">{lines.map((line) => <tr key={`${line.description}-${line.unitPrice}`}><td className="px-5 py-5"><p className="font-semibold text-[#0a1b36]">{line.description}</p>{line.detail && <p className="mt-1 text-xs leading-5 text-[#60708a]">{line.detail}</p>}</td><td className="px-4 py-5 text-center">{line.quantity}</td><td className="px-4 py-5 text-right">{formatMoney(line.unitPrice)}</td><td className="px-5 py-5 text-right font-semibold">{formatMoney(line.quantity * line.unitPrice)}</td></tr>)}</tbody></table></div>
        <div className="mt-7 ml-auto max-w-sm rounded-2xl bg-[#f5f7fb] p-5"><div className="flex justify-between text-sm text-[#60708a]"><span>Subtotal</span><span>{formatMoney(subtotal)}</span></div><div className="mt-3 flex justify-between text-sm text-[#60708a]"><span>Tax</span><span>Included where applicable</span></div><div className="mt-4 flex justify-between border-t border-[#cfd9e6] pt-4 text-xl font-bold text-[#07152d]"><span>Total</span><span>{formatMoney(subtotal)}</span></div></div>
        <div className="mt-10 grid gap-5 sm:grid-cols-2"><div className="rounded-2xl border border-[#dce4ef] p-5"><p className="text-xs font-bold uppercase tracking-[.14em] text-[#1f5bbd]">Payment note</p><p className="mt-3 text-sm leading-6 text-[#60708a]">Course access is activated only after payment has been securely verified. Never send passwords, card details or one-time PINs by email.</p></div><div className="rounded-2xl bg-[#fff7df] p-5"><p className="text-xs font-bold uppercase tracking-[.14em] text-[#8a6000]">Need help?</p><p className="mt-3 text-sm leading-6 text-[#6d5a2a]">Contact Amaris and include the invoice number shown above so we can assist you quickly.</p></div></div>
      </div>
      <BrandDocumentFooter reference={invoiceNumber} />
    </article>
  );
}
