"use client";

import { useActionState } from "react";
import { saveWhatsAppPreference } from "./actions";

export function PreferenceForm({ number, optedIn }: { number: string; optedIn: boolean }) {
  const [state, action, pending] = useActionState(saveWhatsAppPreference, { message: "", error: false });
  return <form action={action} className="space-y-5 rounded-2xl border bg-white p-6">
    <label className="block text-sm font-semibold" htmlFor="whatsapp-number">WhatsApp number (international format)</label>
    <input id="whatsapp-number" name="number" type="tel" defaultValue={number}
      placeholder="+27821234567" className="w-full rounded-lg border p-3" />
    <label className="flex items-start gap-3 text-sm">
      <input name="opted_in" type="checkbox" defaultChecked={optedIn} className="mt-1" />
      <span>I agree to receive Amaris lesson booking confirmations and reminders on WhatsApp. I can withdraw consent here at any time. Email notifications will continue.</span>
    </label>
    <button type="submit" disabled={pending} className="rounded-lg bg-blue-700 px-5 py-3 font-semibold text-white disabled:opacity-50">{pending ? "Saving…" : "Save WhatsApp preferences"}</button>
    {state.message && <p role="status" className={state.error ? "text-red-700" : "text-green-700"}>{state.message}</p>}
  </form>;
}
