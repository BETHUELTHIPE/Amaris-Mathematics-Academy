"use client";

import { useActionState } from "react";
import { sendHappyForm } from "./actions";

const initialState = { ok: false, message: "" };

export function FeedbackForm() {
  const [state, action, pending] = useActionState(async (_previous: typeof initialState, form: FormData) => sendHappyForm(form), initialState);
  return <form action={action} className="mx-auto max-w-xl space-y-5 rounded-2xl border bg-white p-6 shadow-sm">
    <h1 className="text-2xl font-bold">How did we do? 😊</h1>
    <p className="text-sm text-slate-600">Your feedback helps our tutors and academy improve.</p>
    <label className="block text-sm font-medium">Service received
      <select name="service" required className="mt-1 block w-full rounded-lg border p-3">
        <option value="live_class">Zoom online lesson</option>
        <option value="course">Purchased course or learning materials</option>
      </select>
    </label>
    <label className="block text-sm font-medium">Booking reference or course slug
      <input name="reference" required maxLength={100} className="mt-1 block w-full rounded-lg border p-3" placeholder="From your booking or course confirmation"/>
    </label>
    <label className="block text-sm font-medium">Overall experience
      <select name="overall_rating" required defaultValue="" className="mt-1 block w-full rounded-lg border p-3">
        <option value="" disabled>Choose 1 to 5 stars</option>
        {[5,4,3,2,1].map(v=><option key={v} value={v}>{v} star{v===1?"":"s"}</option>)}
      </select>
    </label>
    <label className="block text-sm font-medium">Tutor rating (Zoom lessons only)
      <select name="tutor_rating" defaultValue="" className="mt-1 block w-full rounded-lg border p-3">
        <option value="">Not applicable</option>
        {[5,4,3,2,1].map(v=><option key={v} value={v}>{v} star{v===1?"":"s"}</option>)}
      </select>
    </label>
    <label className="block text-sm font-medium">Any suggestions? (optional)
      <textarea name="comments" maxLength={1000} rows={3} className="mt-1 block w-full rounded-lg border p-3" placeholder="Tell us what went well or what we could improve." />
    </label>
    {state.message && <p role="status" className="text-sm">{state.message}</p>}
    <button disabled={pending || state.ok} type="submit" className="rounded-xl bg-slate-900 px-6 py-3 font-semibold text-white disabled:opacity-50">{pending ? "Sending..." : state.ok ? "Feedback received" : "Send feedback"}</button>
  </form>;
}
