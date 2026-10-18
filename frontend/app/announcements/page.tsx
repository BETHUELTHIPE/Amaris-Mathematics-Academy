import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { AnnouncementYouTube } from "@/components/site/announcement-youtube";

type Media = { id: number; title: string; kind: "image" | "video" | "pdf"; download_url: string };
type Announcement = { id: number; title: string; message: string; link_url: string; link_label: string; youtube_url?: string; media: Media[] };
const cms = process.env.CMS_API_URL?.replace(/\/$/, "");

async function publishedAnnouncements(): Promise<Announcement[]> {
  if (!cms) return [];
  try {
    const response = await fetch(`${cms}/announcements/`, { next: { revalidate: 60 }, signal: AbortSignal.timeout(4000) });
    if (!response.ok) return [];
    const data: unknown = await response.json();
    return Array.isArray(data) ? data as Announcement[] : [];
  } catch { return []; }
}

export const metadata = { title: "Announcements & News | Amaris Mathematics Academy" };

export default async function AnnouncementsPage() {
  const announcements = await publishedAnnouncements();
  return <main className="min-h-screen bg-[#f5f7fb] text-[#07152d]">
    <Header />
    <section className="bg-[#07152d] px-5 py-16 text-white lg:px-8">
      <div className="mx-auto max-w-6xl">
        <p className="font-bold uppercase tracking-widest text-[#ffcc66]">Amaris Newsroom</p>
        <h1 className="mt-3 text-4xl font-bold sm:text-6xl">Announcements & opportunities</h1>
        <p className="mt-5 max-w-2xl text-white/70">Discover updates, special programmes, learning opportunities and announcements from Amaris Mathematics Academy.</p>
      </div>
    </section>
    <section className="mx-auto grid max-w-6xl gap-7 px-5 py-12 lg:px-8">
      {announcements.length === 0 && <p className="rounded-2xl bg-white p-8">There are no published announcements at this time.</p>}
      {announcements.map(a => <article key={a.id} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-9">
        <h2 className="text-2xl font-bold">{a.title}</h2>
        <p className="mt-4 whitespace-pre-line leading-7 text-slate-600">{a.message}</p>
        <AnnouncementYouTube url={a.youtube_url} title={a.title} />
        <div className="mt-6 grid gap-5 md:grid-cols-2">
          {(a.media ?? []).map(m => {
            const url = new URL(m.download_url, cms ?? "https://invalid.example").toString();
            return <div key={m.id} className="overflow-hidden rounded-2xl border border-slate-200">
              {m.kind === "image" && <img src={url} alt={m.title} loading="lazy" className="h-auto w-full object-cover" />}
              {m.kind === "video" && <video src={url} controls preload="none" aria-label={m.title} className="w-full" />}
              {m.kind === "pdf" && <a href={url} target="_blank" rel="noopener noreferrer" className="block p-5 font-semibold text-blue-700 underline">View PDF: {m.title}</a>}
            </div>;
          })}
        </div>
        {a.link_url && (/^\//.test(a.link_url) || /^https:\/\//.test(a.link_url)) && <a className="mt-7 inline-block rounded-full bg-[#07152d] px-6 py-3 font-bold text-white" href={a.link_url} rel="noopener noreferrer">{a.link_label || "Learn more"}</a>}
      </article>)}
    </section>
    <Footer />
  </main>;
}
