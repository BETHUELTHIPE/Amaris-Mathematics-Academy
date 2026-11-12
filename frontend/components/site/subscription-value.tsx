import { BookOpen, Video } from "lucide-react";
import { subscriptionSupport } from "@/lib/subscription-plans";

export function SubscriptionValue() {
  return (
    <section aria-label="Your weekly learning rhythm" className="mt-10 rounded-3xl border border-[#dce4ef] bg-[#edf3ff] p-6 sm:p-9">
      <p className="text-xs font-bold uppercase tracking-[.16em] text-[#1f5bbd]">What your investment gives you</p>
      <h2 className="mt-3 text-2xl font-semibold tracking-tight text-[#07152d] sm:text-3xl">Two focused sessions. One steady learning rhythm.</h2>
      <p className="mt-4 max-w-3xl text-sm leading-7 text-[#425674]">Your plan brings four hours of one-to-one Zoom tutoring each week together with course access. Spend time understanding a topic, then return to practise it with support. The same weekly support is included in both plans, for every curriculum.</p>
      <div className="mt-7 grid gap-4 md:grid-cols-2">
        {subscriptionSupport.sessions.map((session, index) => (
          <article key={session.title} className="rounded-2xl border border-[#dce4ef] bg-white p-5 sm:p-6">
            <p className="flex items-center gap-2 text-sm font-bold text-[#1f5bbd]"><Video aria-hidden="true" className="size-4 shrink-0" />Session {index + 1} · {subscriptionSupport.minutesPerSession / 60} hours · One-to-one</p>
            <h3 className="mt-3 text-xl font-semibold text-[#07152d]">{session.title}</h3>
            <p className="mt-3 text-sm leading-7 text-[#60708a]">{session.description}</p>
          </article>
        ))}
      </div>
      <p className="mt-6 flex items-start gap-3 text-sm leading-7 text-[#425674]"><BookOpen aria-hidden="true" className="mt-1 size-5 shrink-0" /><span><strong className="text-[#07152d]">Keep learning between sessions.</strong> Revisit published courses in your selected curriculum, practise questions and pick up where you left off with saved progress.</span></p>
    </section>
  );
}
