import type { Metadata } from "next";
import Link from "next/link";
import { ArrowDown, ArrowRight, Bell, BookOpen, CalendarDays, Check, Clock3, GraduationCap, Megaphone, Search, ShieldCheck, Sparkles } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { getManagedAnnouncements } from "@/lib/cms";
import { announcementDeadline, filterAnnouncements, safeAnnouncementLink, type Announcement } from "@/lib/announcements";

export const metadata: Metadata = {
  title: "Announcements",
  description: "Official Amaris Mathematics Academy announcements, important notices and learning updates. Find your next step, all in one place.",
};

const focusRing = "focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#1f5bbd]";
const darkFocusRing = "focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#ffcc66]";

function NoticeLink({ notice, light = false }: { notice: Announcement; light?: boolean }) {
  const href = safeAnnouncementLink(notice.link_url);
  if (!href) return null;
  const external = href.startsWith("https:");
  return <a href={href} target={external ? "_blank" : undefined} rel={external ? "noopener noreferrer" : undefined}
    className={`mt-6 inline-flex min-h-11 items-center gap-3 rounded-full px-5 py-3 text-sm font-bold ${light ? darkFocusRing : focusRing} ${light ? "bg-[#ffcc66] text-[#07152d] hover:bg-[#ffda8f]" : "bg-[#edf3ff] text-[#184b9e] hover:bg-[#dfeaff]"}`}>
    {notice.link_label || "Learn more"}<ArrowRight aria-hidden="true" className="size-4 shrink-0" />
    {external && <span className="sr-only"> (opens in a new tab)</span>}
  </a>;
}

function Deadline({ notice }: { notice: Announcement }) {
  const deadline = announcementDeadline(notice.expires_at);
  if (!deadline) return null;
  return <p className="mt-5 flex items-start gap-2 text-xs leading-5"><Clock3 aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
    <span>Notice available until <time dateTime={notice.expires_at!}>{deadline}</time> SAST</span>
  </p>;
}

export default async function AnnouncementsPage({ searchParams }: {
  searchParams: Promise<{ q?: string | string[]; filter?: string | string[] }>;
}) {
  const [announcements, params] = await Promise.all([getManagedAnnouncements(), searchParams]);
  const query = (typeof params.q === "string" ? params.q : "").trim().slice(0, 160);
  const priorityOnly = params.filter === "priority";
  const notices = announcements ?? [];
  const filtered = filterAnnouncements(notices, query, priorityOnly);
  const featured = !query && !priorityOnly ? notices[0] : undefined;
  const feed = featured ? filtered.filter((notice) => notice.id !== featured.id) : filtered;
  const priorityCount = notices.filter((notice) => notice.priority > 0).length;
  const filterUrl = (priority: boolean) => {
    const search = new URLSearchParams();
    if (query) search.set("q", query);
    if (priority) search.set("filter", "priority");
    return `/announcements${search.size ? `?${search}` : ""}#updates`;
  };

  return <>
    <Header />
    <main id="main-content" className="min-h-screen bg-[#f5f7fb] text-[#07152d]">
      <section aria-labelledby="announcements-title" className="relative isolate overflow-hidden bg-[#07152d] text-white">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(43,101,190,.3),transparent_65%)]" />
        <div className="relative mx-auto grid max-w-7xl gap-12 px-5 pb-16 pt-12 sm:pb-20 lg:grid-cols-[1.2fr_.8fr] lg:gap-16 lg:px-8 lg:pt-16">
          <div>
            <nav aria-label="Breadcrumb" className="mb-10 flex items-center gap-3 text-xs text-[#bdcbe0]">
              <Link href="/" className={`hover:text-white ${darkFocusRing}`}>Home</Link><span aria-hidden="true">/</span><span aria-current="page">Announcements</span>
            </nav>
            <p className="inline-flex items-center gap-2 rounded-full border border-[#ffcc66]/30 bg-[#ffcc66]/10 px-3 py-2 text-[11px] font-bold uppercase tracking-[.16em] text-[#ffcc66]"><span className="size-1.5 rounded-full bg-[#ffcc66]" />The Amaris noticeboard</p>
            <h1 id="announcements-title" className="mt-6 max-w-2xl text-5xl font-semibold leading-[1.08] tracking-[-.045em] sm:text-6xl lg:text-7xl">Stay informed.<br /><span className="text-[#ffcc66]">Keep moving forward.</span></h1>
            <p className="mt-6 max-w-xl text-base leading-8 text-[#bdcbe0] sm:text-lg">Your place for official academy notices, learning updates and the details that matter to your next step.</p>
            <a href="#updates" className={`mt-8 inline-flex min-h-11 items-center gap-3 rounded-full bg-white px-6 py-3.5 text-sm font-bold text-[#07152d] hover:bg-[#e8eef8] ${darkFocusRing}`}>Explore announcements<ArrowDown aria-hidden="true" className="size-4" /></a>
          </div>
          <div className="relative self-center lg:pt-10">
            <div aria-hidden="true" className="absolute -right-14 -top-8 size-64 rounded-full border border-white/10 sm:size-80" />
            <div className="relative rounded-[1.75rem] border border-white/15 bg-[#10274a] p-7 shadow-2xl sm:p-8">
              <div className="flex items-center justify-between gap-4"><span className="grid size-12 place-items-center rounded-2xl bg-[#ffcc66] text-[#07152d]"><Megaphone aria-hidden="true" className="size-6" /></span><span className="rounded-full border border-white/20 px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-[#d9e5f6]">Academy updates</span></div>
              <p className="mt-8 text-xs font-bold uppercase tracking-[.17em] text-[#ffcc66]">A little clarity. A lot of progress.</p>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl">The right information.<br />All in one place.</h2>
              <div className="mt-7 space-y-4 border-t border-white/15 pt-6 text-sm text-[#d0dcee]">
                {["Published by Amaris Mathematics Academy", "Important notices easy to find", "For school, TVET and university learners"].map((text) => <p key={text} className="flex items-start gap-3"><Check aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-[#ffcc66]" />{text}</p>)}
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="border-b border-[#dce4ef] bg-white"><div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-8 gap-y-3 px-5 py-5 text-xs font-semibold text-[#455874] lg:px-8">
        <span className="flex items-center gap-2"><ShieldCheck aria-hidden="true" className="size-4 text-[#1f5bbd]" />Official academy notices</span>
        <span className="flex items-center gap-2"><GraduationCap aria-hidden="true" className="size-4 text-[#1f5bbd]" />CAPS · IEB · TVET · University</span>
        <span className="flex items-center gap-2"><Clock3 aria-hidden="true" className="size-4 text-[#1f5bbd]" />Times shown in South African time</span>
      </div></div>

      <section id="updates" aria-labelledby="updates-heading" className="mx-auto max-w-7xl scroll-mt-64 px-5 py-14 lg:px-8 lg:py-20">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-6"><div><p className="text-xs font-bold uppercase tracking-[.16em] text-[#1f5bbd]">From the academy</p><h2 id="updates-heading" className="mt-3 text-3xl font-semibold tracking-[-.035em] sm:text-4xl">Your latest updates</h2></div>
          <p className="max-w-sm text-sm leading-6 text-[#52647f]">Clear information to help you plan your learning with confidence.</p></div>
        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div className="min-w-0">
            <form action="/announcements#updates" method="get" role="search" className="rounded-2xl border border-[#dce4ef] bg-white p-4 sm:p-5">
              <label htmlFor="announcement-search" className="mb-2 block text-xs font-bold text-[#455874]">Search academy notices</label>
              <div className="flex flex-wrap gap-3"><div className="relative min-w-0 flex-1 basis-48"><Search aria-hidden="true" className="pointer-events-none absolute left-3.5 top-3.5 size-4 text-[#52647f]" /><input id="announcement-search" name="q" type="search" defaultValue={query} maxLength={160} placeholder="Search by title or keyword…" className={`min-h-11 w-full rounded-xl border border-[#bac8dc] bg-[#f8faff] py-3 pl-10 pr-3 text-sm ${focusRing}`} /></div>
                {priorityOnly && <input type="hidden" name="filter" value="priority" />}
                <button type="submit" className={`min-h-11 rounded-xl bg-[#0b2a5b] px-5 py-3 text-sm font-bold text-white hover:bg-[#153d77] ${focusRing}`}>Search</button></div>
            </form>
            <nav aria-label="Announcement filters" className="mt-5 flex flex-wrap gap-2">
              {[[false, "All updates", notices.length], [true, "Priority notices", priorityCount]].map(([priority, label, count]) => <a key={String(label)} href={filterUrl(priority as boolean)} aria-current={priorityOnly === priority ? "page" : undefined}
                className={`inline-flex min-h-11 items-center gap-2 rounded-full border px-4 py-2 text-xs font-bold ${focusRing} ${priorityOnly === priority ? "border-[#0b2a5b] bg-[#0b2a5b] text-white" : "border-[#d1dcea] bg-white text-[#455874] hover:border-[#1f5bbd]"}`}>{label}<span className="rounded-full bg-current/10 px-2 py-0.5">{announcements === null ? "—" : count}</span></a>)}
            </nav>
            {announcements === null ? <div role="status" className="mt-6 rounded-2xl border border-[#e6cd94] bg-[#fff9ec] p-7"><Bell aria-hidden="true" className="size-6 text-[#80560c]" /><h3 className="mt-4 text-xl font-semibold">We couldn’t load the notices.</h3><p className="mt-3 text-sm leading-7 text-[#66522f]">Please try again shortly. If you need help with a class or your account, our team can assist.</p><a href="/announcements" className={`mt-5 inline-flex min-h-11 items-center rounded-full border border-[#987331] px-5 text-sm font-bold ${focusRing}`}>Try again</a></div> : <>
              {(query || priorityOnly) && <p role="status" className="mt-6 break-words text-sm text-[#455874]">{filtered.length} {filtered.length === 1 ? "notice" : "notices"}{query ? ` matching “${query}”` : " in priority notices"}. <a href="/announcements#updates" className={`ml-2 inline-flex min-h-11 items-center font-bold text-[#184b9e] underline underline-offset-4 ${focusRing}`}>Clear filters</a></p>}
              {featured && <article className="mt-6 overflow-hidden rounded-[1.5rem] border border-[#1e4276] bg-[#0b2a5b] text-white">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/15 px-6 py-4 text-xs sm:px-8"><span className="flex items-center gap-2 font-bold uppercase tracking-[.13em] text-[#ffcc66]"><Sparkles aria-hidden="true" className="size-4" />Featured notice</span><span className="text-[#d0dcee]">{featured.priority > 0 ? "Priority announcement" : "Academy announcement"}</span></div>
                <div className="p-6 sm:p-8"><h3 className="break-words text-2xl font-semibold leading-snug tracking-tight sm:text-3xl">{featured.title}</h3><p className="mt-5 whitespace-pre-wrap break-words text-sm leading-8 text-[#d0dcee]">{featured.message}</p><NoticeLink notice={featured} light /><div className="text-[#c0d0e7]"><Deadline notice={featured} /></div></div>
              </article>}
              <div className="mt-6 space-y-4">{feed.map((notice) => <article key={notice.id} className="rounded-2xl border border-[#dce4ef] bg-white p-6 sm:p-7">
                <div className="mb-4 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[.13em] text-[#184b9e]"><Bell aria-hidden="true" className="size-4" />{notice.priority > 0 ? "Priority notice" : "Academy update"}</div>
                <h3 className="break-words text-xl font-semibold leading-snug tracking-tight">{notice.title}</h3><p className="mt-3 whitespace-pre-wrap break-words text-sm leading-7 text-[#455874]">{notice.message}</p><NoticeLink notice={notice} /><div className="text-[#52647f]"><Deadline notice={notice} /></div>
              </article>)}</div>
              {!filtered.length && <div className="mt-6 rounded-[1.5rem] border border-dashed border-[#b9c9de] bg-white px-6 py-14 text-center"><span className="mx-auto grid size-16 place-items-center rounded-2xl bg-[#edf3ff]"><Megaphone aria-hidden="true" className="size-7 text-[#1f5bbd]" /></span><h3 className="mt-6 text-2xl font-semibold tracking-tight">{query || priorityOnly ? "No notices match just yet." : "A quiet noticeboard. A clear path ahead."}</h3><p className="mx-auto mt-3 max-w-md text-sm leading-7 text-[#52647f]">{query || priorityOnly ? "Try a different keyword or view all announcements." : "There are no published announcements at the moment. New academy notices will appear here when they are published."}</p><Link href={query || priorityOnly ? "/announcements#updates" : "/courses"} className={`mt-6 inline-flex min-h-11 items-center gap-2 rounded-full bg-[#0b2a5b] px-5 py-3 text-sm font-bold text-white ${focusRing}`}>{query || priorityOnly ? "View all updates" : "Explore your next course"}<ArrowRight aria-hidden="true" className="size-4" /></Link></div>}
            </>}
          </div>

          <aside aria-label="Learning and support links" className="space-y-5">
            <div className="rounded-2xl border border-[#ead8b0] bg-[#fff6e3] p-6"><p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[.13em] text-[#735014]"><BookOpen aria-hidden="true" className="size-4" />Your next step</p><h2 className="mt-4 text-2xl font-semibold tracking-tight">Make room for progress.</h2><p className="mt-3 text-sm leading-7 text-[#665532]">Find the learning format that fits the topic you want to understand.</p>
              <div className="mt-6 divide-y divide-[#e6d6b5]">{[
                { href: "/courses", icon: GraduationCap, title: "Explore courses", copy: "Find your programme and level" },
                { href: "/book-online-live-class", icon: CalendarDays, title: "Book a live class", copy: "Choose a tutor’s available time" },
                { href: "/request-a-video", icon: BookOpen, title: "Request a topic video", copy: "Focus on a topic you need" },
              ].map(({ href, icon: Icon, title, copy }) => <Link key={href} href={href} className={`flex min-h-16 items-center gap-3 py-4 ${focusRing}`}><Icon aria-hidden="true" className="size-5 shrink-0 text-[#80560c]" /><span className="min-w-0 flex-1"><span className="block text-sm font-bold">{title}</span><span className="mt-1 block text-xs leading-5 text-[#665532]">{copy}</span></span><ArrowRight aria-hidden="true" className="size-4 shrink-0" /></Link>)}</div>
            </div>
            <div className="rounded-2xl border border-[#dce4ef] bg-white p-6"><ShieldCheck aria-hidden="true" className="size-6 text-[#1f5bbd]" /><h2 className="mt-4 text-lg font-semibold">A note on your privacy</h2><p className="mt-3 text-sm leading-7 text-[#52647f]">This is a public noticeboard. For personal booking, payment or account questions, contact our team directly.</p><Link href="/contact" className={`mt-4 inline-flex min-h-11 items-center gap-2 text-sm font-bold text-[#184b9e] ${focusRing}`}>Contact the academy<ArrowRight aria-hidden="true" className="size-4" /></Link></div>
          </aside>
        </div>
      </section>
      <section aria-labelledby="help-heading" className="px-5 pb-16 lg:px-8 lg:pb-24"><div className="mx-auto flex max-w-7xl flex-col justify-between gap-6 rounded-[1.5rem] bg-[#e6edf8] p-7 sm:p-10 md:flex-row md:items-center"><div><p className="text-xs font-bold uppercase tracking-[.15em] text-[#184b9e]">We’re here to help</p><h2 id="help-heading" className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl">Need a little more clarity?</h2><p className="mt-3 text-sm leading-7 text-[#455874]">Ask about your learning options, a notice, or your next step at Amaris.</p></div><Link href="/contact" className={`inline-flex min-h-11 w-fit shrink-0 items-center gap-3 rounded-full bg-[#0b2a5b] px-6 py-3.5 text-sm font-bold text-white ${focusRing}`}>Let’s talk<ArrowRight aria-hidden="true" className="size-4" /></Link></div></section>
    </main>
    <Footer />
  </>;
}
