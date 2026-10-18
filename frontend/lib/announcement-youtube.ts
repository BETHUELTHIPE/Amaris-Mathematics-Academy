export type AnnouncementYouTube = { watchUrl: string; embedUrl: string; kind: "video" | "playlist" };

/** Rebuild all destinations from validated IDs; never render a pasted iframe URL. */
export function announcementYouTube(value: unknown): AnnouncementYouTube | null {
  if (typeof value !== "string") return null;
  const input = value.trim();
  if (!input || /[\s\\\u0000-\u001f\u007f]/.test(input)) return null;
  try {
    const url = new URL(input);
    if (url.protocol !== "https:" || url.username || url.password || url.port) return null;
    const parts = url.pathname.replace(/^\/+|\/+$/g, "").split("/");
    let video = "";
    let playlist = "";
    if (url.hostname === "youtu.be" && parts.length === 1) video = parts[0];
    else if (url.hostname === "studio.youtube.com" && parts.length === 3) {
      if (parts[0] === "playlist" && parts[2] === "videos") playlist = parts[1];
      else if (parts[0] === "video" && parts[2] === "edit") video = parts[1];
    } else if (["youtube.com", "www.youtube.com", "m.youtube.com", "www.youtube-nocookie.com"].includes(url.hostname)) {
      if (parts.length === 1 && parts[0] === "watch") video = url.searchParams.get("v") ?? "";
      else if (parts.length === 2 && ["shorts", "live", "embed"].includes(parts[0]) && parts[1] !== "videoseries") video = parts[1];
      else if ((parts.length === 1 && ["playlist", "embed"].includes(parts[0])) || (parts[0] === "embed" && parts[1] === "videoseries" && parts.length === 2)) playlist = url.searchParams.get("list") ?? "";
    }
    if (/^[A-Za-z0-9_-]{11}$/.test(video)) return {
      kind: "video", watchUrl: `https://www.youtube.com/watch?v=${video}`,
      embedUrl: `https://www.youtube-nocookie.com/embed/${video}?playsinline=1`,
    };
    if (/^[A-Za-z0-9_-]{10,128}$/.test(playlist)) return {
      kind: "playlist", watchUrl: `https://www.youtube.com/playlist?list=${playlist}`,
      embedUrl: `https://www.youtube-nocookie.com/embed/videoseries?list=${playlist}&playsinline=1`,
    };
  } catch { /* Malformed CMS input must not break the public noticeboard. */ }
  return null;
}
