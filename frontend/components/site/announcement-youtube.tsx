import { announcementYouTube } from "@/lib/announcement-youtube";

export function AnnouncementYouTube({ url, title, light = false }: { url?: unknown; title: string; light?: boolean }) {
  const video = announcementYouTube(url);
  if (!video) return null;
  return <section className="mt-6 overflow-hidden rounded-2xl border border-current/20" aria-label={`YouTube: ${title}`}>
    <iframe
      src={video.embedUrl}
      title={`${title} — YouTube ${video.kind}`}
      loading="lazy"
      referrerPolicy="strict-origin-when-cross-origin"
      allow="encrypted-media; picture-in-picture; fullscreen"
      allowFullScreen
      className="aspect-video min-h-[200px] w-full border-0 bg-black"
    />
    <a href={video.watchUrl} target="_blank" rel="noopener noreferrer"
      className={`flex min-h-11 items-center px-5 py-4 text-sm font-bold underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 ${light ? "text-white" : "text-[#184b9e]"}`}>
      Open {video.kind === "playlist" ? "playlist" : "video"} on YouTube
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  </section>;
}
