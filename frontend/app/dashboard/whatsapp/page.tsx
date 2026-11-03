import type { Metadata } from "next";
import Link from "next/link";
import { requireVerifiedStudent } from "@/lib/auth";
import { getStudentWhatsAppPreference } from "@/lib/student-api";
import { PreferenceForm } from "./preference-form";

export const metadata: Metadata = { title: "WhatsApp notifications" };
export const dynamic = "force-dynamic";

export default async function WhatsAppSettingsPage() {
  await requireVerifiedStudent("/dashboard/whatsapp");
  let preference = { number: "", opted_in: false };
  try { preference = await getStudentWhatsAppPreference(); } catch {
    return <main className="mx-auto max-w-2xl px-5 py-12">
      <Link href="/dashboard" className="text-sm text-blue-700">Back to dashboard</Link>
      <h1 className="my-5 text-3xl font-semibold">WhatsApp lesson notifications</h1>
      <p role="alert" className="rounded-xl border border-amber-300 bg-amber-50 p-5 text-amber-900">WhatsApp preferences are temporarily unavailable. No settings have been changed. Please try again later.</p>
    </main>;
  }
  return <main className="mx-auto max-w-2xl px-5 py-12">
    <Link href="/dashboard" className="text-sm text-blue-700">Back to dashboard</Link>
    <h1 className="my-5 text-3xl font-semibold">WhatsApp lesson notifications</h1>
    <p className="mb-6 text-slate-600">Choose whether Amaris Mathematics Academy can send booking confirmations and class reminders to your WhatsApp number. You can opt out whenever you wish.</p>
    <PreferenceForm number={preference.number} optedIn={preference.opted_in} />
  </main>;
}
