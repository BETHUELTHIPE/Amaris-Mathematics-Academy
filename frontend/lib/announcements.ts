export type AnnouncementMedia = {
  id: number;
  title: string;
  kind: "image" | "video" | "pdf";
  order: number;
  download_url: string;
};

export function safeCmsMediaUrl(value: string, cmsApiUrl?: string): string | null {
  if (!cmsApiUrl || !value || /[\\\\\u0000-\u001f\u007f]/.test(value)) return null;
  try {
    const base = new URL(cmsApiUrl);
    const target = new URL(value, base);
    if (base.protocol !== "https:" || target.protocol !== "https:" || target.origin !== base.origin) return null;
    if (!/^\\/api\\/v1\\/marketing-media\\/\\d+\\/$/.test(target.pathname)) return null;
    if (target.search || target.hash || target.username || target.password) return null;
    return target.href;
  } catch {
    return null;
  }
}

export type Announcement = {
  id: number;
  title: string;
  message: string;
  link_label: string;
  link_url: string;
  priority: number;
  expires_at: string | null;
  media?: AnnouncementMedia[];
};

export function safeAnnouncementLink(value: string): string | null {
  const url = value.trim();
  if (!url || /[\s\\\u0000-\u001f\u007f]/.test(url)) return null;
  if (url.startsWith("/") && !url.startsWith("//")) return url;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && !parsed.username && !parsed.password ? parsed.href : null;
  } catch {
    return null;
  }
}

export function prepareAnnouncements(value: unknown, now = Date.now()): Announcement[] | null {
  if (!Array.isArray(value)) return null;
  return value.filter((item): item is Announcement => {
    if (!item || typeof item !== "object") return false;
    const valid = Number.isSafeInteger(item.id) && typeof item.title === "string" &&
      typeof item.message === "string" && typeof item.link_label === "string" &&
      typeof item.link_url === "string" && typeof item.priority === "number" &&
      Number.isFinite(item.priority) && (item.expires_at === null || typeof item.expires_at === "string");
    return valid && (item.expires_at === null || Date.parse(item.expires_at) > now);
  }).map((item) => ({
    ...item,
    media: Array.isArray(item.media) ? item.media.filter((asset: unknown): asset is AnnouncementMedia => {
      if (!asset || typeof asset !== "object") return false;
      const candidate = asset as Record<string, unknown>;
      return Number.isSafeInteger(candidate.id) && typeof candidate.title === "string" &&
        typeof candidate.download_url === "string" &&
        ["image", "video", "pdf"].includes(String(candidate.kind)) &&
        Number.isSafeInteger(candidate.order);
    }) : [],
  })).sort((a, b) => b.priority - a.priority || b.id - a.id);
}

export function filterAnnouncements(items: Announcement[], query: string, priorityOnly: boolean) {
  const search = query.trim().toLocaleLowerCase("en-ZA");
  return items.filter((item) => (!priorityOnly || item.priority > 0) &&
    (!search || `${item.title} ${item.message}`.toLocaleLowerCase("en-ZA").includes(search)));
}

export function announcementDeadline(value: string | null): string | null {
  if (!value || !Number.isFinite(Date.parse(value))) return null;
  return new Intl.DateTimeFormat("en-ZA", {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    timeZone: "Africa/Johannesburg",
  }).format(new Date(value));
}
