import Link from "next/link";
import type { TutorEarnings } from "@/lib/tutor-api";

const money = (value: string) => new Intl.NumberFormat("en-ZA", {
  style: "currency", currency: "ZAR", minimumFractionDigits: 2,
}).format(Number(value));

export function TutorEarningsPanel({ earnings }: { earnings: TutorEarnings | null }) {
  return <section id="earnings" aria-labelledby="tutor-earnings-title" className="min-w-0 rounded-3xl border border-[#dce4ef] bg-white p-5 sm:p-8">
    <p className="eyebrow">Your earnings, clearly explained</p>
    <h2 id="tutor-earnings-title" className="mt-2 text-3xl font-semibold tracking-tight">Payments &amp; service activity</h2>
    <p className="mt-3 max-w-3xl text-sm leading-7 text-[#60708a]">See verified sales and your agreed share for each service. Student identities are kept private in this financial summary.</p>
    {!earnings ? <div role="status" className="mt-6 rounded-2xl bg-[#f1f5fb] p-5 text-sm leading-7 text-[#263852]">Your earnings could not be loaded. <Link href="/tutor/dashboard#earnings" className="font-bold text-[#1f5bbd] underline">Refresh this summary</Link> or contact the academy. Your timetable remains available below.</div> : <>
      <dl className="mt-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[["Your total earnings", money(earnings.total)], ["Confirmed paid", money(earnings.paid_out)], ["Awaiting settlement", money(earnings.outstanding)], ["Students who paid", String(earnings.unique_students)]].map(([label, value]) => <div key={label} className="min-w-0 rounded-2xl bg-[#f1f5fb] p-5"><dt className="text-sm text-[#60708a]">{label}</dt><dd className="mt-3 break-words text-2xl font-bold text-[#0b2a5b]">{value}</dd></div>)}
      </dl>
      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        {([["course", "Courses sold"], ["live_class", "Online class bookings"], ["video", "Video requests"]] as const).map(([key, label]) => {
          const category = earnings.categories[key];
          return <article key={key} className="min-w-0 rounded-2xl border border-[#dce4ef] p-5"><h3 className="text-lg font-semibold text-[#0b2a5b]">{label}</h3><dl className="mt-5 grid gap-3 text-sm">{[["Paid services", String(category.count)], ["Students who paid", String(category.students)], ["Gross sales", money(category.gross)], ["Your agreed share", money(category.earned)]].map(([name, value]) => <div key={name} className="flex flex-wrap justify-between gap-x-4 gap-y-1"><dt className="text-[#60708a]">{name}</dt><dd className="font-semibold text-[#263852]">{value}</dd></div>)}</dl>{key === "live_class" && <p className="mt-4 border-t border-[#dce4ef] pt-4 text-sm text-[#60708a]">Completed paid sessions: <strong className="text-[#263852]">{earnings.classes_attended}</strong></p>}</article>;
        })}
      </div>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[#dce4ef] p-5 text-sm"><p className="text-[#263852]">Payout account: <strong>{earnings.bank_account_mask || "Not configured"}</strong></p><p className="font-semibold text-[#60708a]">{earnings.recipient_verified ? "Account verified" : "Account verification pending"}</p></div>
      <p className="mt-5 rounded-2xl bg-[#edf3ff] p-5 text-sm leading-7 text-[#263852]">Bank transfers are awaiting setup. Earnings become eligible after service delivery and the settlement period. Payment confirmations are sent only after a transfer is verified.</p>
    </>}
  </section>;
}
