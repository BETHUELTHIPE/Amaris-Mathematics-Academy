import { BrandDocumentFooter, BrandLetterhead } from "@/components/documents/brand-letterhead";

export function CommunicationDocument({ recipientName, recipientEmail, date }: { recipientName: string; recipientEmail: string; date: string }) {
  return (
    <article className="print-sheet flex min-h-[1120px] flex-col overflow-hidden rounded-[1.75rem] bg-white shadow-[0_24px_80px_rgba(7,21,45,.14)] ring-1 ring-[#dce4ef] print:min-h-screen print:rounded-none print:shadow-none print:ring-0">
      <BrandLetterhead documentLabel="Official communication" />
      <div className="flex-1 px-8 py-10 text-[15px] leading-8 text-[#35445c] sm:px-10"><div className="grid gap-1 text-sm"><p><span className="font-semibold text-[#07152d]">Date:</span> {date}</p><p><span className="font-semibold text-[#07152d]">To:</span> {recipientName}</p><p><span className="font-semibold text-[#07152d]">Email:</span> {recipientEmail}</p></div><h1 className="mt-10 text-2xl font-bold tracking-[-.025em] text-[#07152d]">Official communication template</h1><p className="mt-7">Dear {recipientName},</p><p className="mt-5">Thank you for learning with Amaris Mathematics Academy. Official notices, enrolment confirmations, payment correspondence, learning reports and supporting documents will use this approved letterhead.</p><p className="mt-5">Each communication will clearly identify the academy, show verified contact details and include the relevant student, order or document reference where applicable.</p><div className="mt-8 rounded-2xl border-l-4 border-[#ffcc66] bg-[#f6f8fc] px-6 py-5 text-sm leading-7 text-[#526078]">This is a letterhead preview. Final communication content will be generated from the relevant student action or academy workflow.</div><p className="mt-10">Kind regards,</p><p className="mt-1 font-bold text-[#07152d]">Bethuel Moukangwe</p><p className="text-sm text-[#60708a]">Managing Director<br />Amaris Mathematics Academy</p></div>
      <BrandDocumentFooter reference="COMMUNICATION TEMPLATE" />
    </article>
  );
}
