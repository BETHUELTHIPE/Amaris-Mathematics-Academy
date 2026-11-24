import type { Metadata } from "next";
import Link from "next/link";
import { ChatThread } from "@/components/site/chat-thread";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { StudentDashboardShell } from "@/components/site/student-dashboard-shell";
import { requireVerifiedStudent } from "@/lib/auth";
import { getChatRooms } from "@/lib/chat-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Messages — Amaris Mathematics Academy",
  robots: { index: false, follow: false },
};

const sessionTime = new Intl.DateTimeFormat("en-ZA", {
  dateStyle: "medium", timeStyle: "short", timeZone: "Africa/Johannesburg",
});
const section = "rounded-2xl border border-[#dce4ef] bg-white p-4 sm:p-5";

function roomUrl(page: number, room: string) {
  return `/dashboard/messages?${new URLSearchParams({ page: String(page), room })}`;
}

export default async function MessagesPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string; room?: string }>;
}) {
  await requireVerifiedStudent("/dashboard/messages");
  const params = await searchParams;
  const requestedPage = Number(params.page);
  const page = Number.isSafeInteger(requestedPage) && requestedPage >= 1 && requestedPage <= 100_000
    ? requestedPage : 1;
  const inbox = await getChatRooms(page);
  const isTutor = inbox?.role === "tutor";
  const booking = inbox?.bookings.find(({ id }) => id === params.room);
  const room = booking?.id ?? "support";
  const content = inbox ? (
    <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <nav className={`${section} h-fit`} aria-label="Conversations">
        <h2 className="mb-3 text-lg font-semibold">Conversations</h2>
        <ul className="grid gap-2">
          {[{ id: "support", topic: "Academy support", participant: "", starts_at: "" }, ...inbox.bookings].map((item) => (
            <li key={item.id}>
              <Link
                href={roomUrl(page, item.id)}
                prefetch={false}
                aria-current={room === item.id ? "page" : undefined}
                className={`block min-h-11 rounded-xl px-3 py-2.5 [overflow-wrap:anywhere] ${room === item.id ? "bg-[#0b2a5b] text-white" : "bg-[#f5f7fb] text-[#173b68] hover:bg-[#eaf2ff]"}`}
              >
                <span className="block text-sm font-semibold">{item.topic}</span>
                {item.starts_at && (
                  <span className="mt-1 block text-xs">{item.participant} · {sessionTime.format(new Date(item.starts_at))}</span>
                )}
              </Link>
            </li>
          ))}
        </ul>
        {inbox.bookings.length === 0 && page === 1 && <p className="mt-3 text-sm text-[#465d78]">Booking chats appear after a lesson is confirmed.</p>}
        {(page > 1 || inbox.has_next) && (
          <div className="mt-3 flex flex-wrap gap-4 text-sm font-semibold text-[#1f5bbd]">
            {page > 1 && <Link href={roomUrl(page - 1, "support")} prefetch={false} className="inline-flex min-h-11 items-center">Previous bookings</Link>}
            {inbox.has_next && <Link href={roomUrl(page + 1, "support")} prefetch={false} className="inline-flex min-h-11 items-center">More bookings</Link>}
          </div>
        )}
      </nav>
      <section aria-labelledby="chat-title" className={`${section} min-w-0`}>
        <h2 id="chat-title" className="text-xl font-semibold [overflow-wrap:anywhere]">{booking?.topic ?? "Academy support"}</h2>
        <p className="mb-4 mt-1 text-sm text-[#465d78] [overflow-wrap:anywhere]">
          {booking ? `${booking.participant} and Academy Admin can see this conversation.` : "Only you and Academy Admin can see this conversation."}
        </p>
        <ChatThread key={booking?.assignment ?? room} room={room} role={inbox.role} assignment={booking?.assignment} />
      </section>
    </div>
  ) : <p role="status" className={section}>Messages are temporarily unavailable. Please refresh to try again.</p>;

  return isTutor ? (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <Link href="/tutor/dashboard" className="inline-flex min-h-11 items-center text-sm font-semibold text-[#1f5bbd]">Back to tutor dashboard</Link>
        <h1 className="mb-5 text-3xl font-semibold text-[#07152d]">Messages</h1>
        {content}
      </div>
      <Footer />
    </main>
  ) : (
    <StudentDashboardShell active="messages" title="Messages" description="Talk to your assigned tutor or contact Academy Admin.">
      {content}
    </StudentDashboardShell>
  );
}
