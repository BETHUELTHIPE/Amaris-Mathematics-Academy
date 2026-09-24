import { cache } from "react";
import { academyBrand, type AcademyBrand } from "@/lib/brand";
import { courses, type Course } from "@/lib/courses";

type CmsNavigationItem = {
  label: string;
  url: string;
  location: "header" | "footer" | "both";
  order: number;
  open_in_new_tab: boolean;
};

type CmsSettings = {
  site_name: string;
  short_name: string;
  managing_director: string;
  logo_url: string | null;
  phone: string;
  email: string;
  address: string;
  business_hours: string;
  website_url: string;
};

type CmsCourse = {
  slug: string;
  title: string;
  curriculum: string;
  academic_level: string;
  price: string;
  short_description: string;
  description?: string;
  outcomes?: string[];
  estimated_hours: number;
  featured: boolean;
  lesson_count: number;
  modules?: Array<{ title: string }>;
};

type Paginated<T> = { results: T[] };
type CmsBootstrap = {
  settings: CmsSettings | null;
  navigation: CmsNavigationItem[];
};

const cmsBaseUrl = process.env.CMS_API_URL?.replace(/\/$/, "");

async function cmsFetch<T>(path: string): Promise<T | null> {
  if (!cmsBaseUrl) return null;
  try {
    const response = await fetch(`${cmsBaseUrl}${path}`, {
      headers: { Accept: "application/json" },
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(4_000),
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

const getManagedBootstrap = cache(async (): Promise<CmsBootstrap | null> =>
  cmsFetch<CmsBootstrap>("/bootstrap/"),
);

function phoneHref(phone: string): string {
  return `tel:${phone.replace(/(?!^\+)\D/g, "")}`;
}

export const getManagedBrand = cache(async (): Promise<AcademyBrand> => {
  const settings = (await getManagedBootstrap())?.settings;
  if (!settings) return academyBrand;
  const addressQuery = encodeURIComponent(settings.address);
  let website = settings.website_url;
  try {
    website = new URL(settings.website_url).hostname;
  } catch {
    // Preserve the configured display value when the URL is incomplete.
  }
  return {
    name: settings.site_name,
    shortName: settings.short_name,
    managingDirector: settings.managing_director,
    phoneDisplay: settings.phone,
    phoneHref: phoneHref(settings.phone),
    whatsappDisplay: academyBrand.whatsappDisplay,
    whatsappHref: academyBrand.whatsappHref,
    email: settings.email,
    emailHref: `mailto:${settings.email}`,
    address: settings.address,
    addressShort: settings.address,
    addressHref: `https://maps.google.com/?q=${addressQuery}`,
    hours: settings.business_hours,
    website,
    websiteHref: settings.website_url,
    logoPath: settings.logo_url || academyBrand.logoPath,
  };
});

const fallbackNavigation: CmsNavigationItem[] = [
  { label: "Courses", url: "/courses", location: "both", order: 10, open_in_new_tab: false },
  { label: "How it works", url: "/how-it-works", location: "both", order: 20, open_in_new_tab: false },
  { label: "Book online live class", url: "/book-online-live-class", location: "both", order: 25, open_in_new_tab: false },
  { label: "Request Your Own Video", url: "/request-your-own-video", location: "header", order: 27, open_in_new_tab: false },
  { label: "Pricing", url: "/pricing", location: "both", order: 30, open_in_new_tab: false },
  { label: "About", url: "/about", location: "both", order: 40, open_in_new_tab: false },
  { label: "Contact", url: "/contact", location: "both", order: 50, open_in_new_tab: false },
];

export const getManagedNavigation = cache(async (location: "header" | "footer") => {
  const managedItems = (await getManagedBootstrap())?.navigation;
  const sourceItems = managedItems?.length ? managedItems : fallbackNavigation;
  const bookingLink: CmsNavigationItem = {
    label: "Book online live class",
    url: "/book-online-live-class",
    location: "both",
    order: 25,
    open_in_new_tab: false,
  };
  let items = sourceItems.some((item) => item.url === bookingLink.url)
    ? sourceItems
    : [...sourceItems, bookingLink];
  const videoRequestLink: CmsNavigationItem = {
    label: "Request Your Own Video",
    url: "/request-your-own-video",
    location: "header",
    order: 27,
    open_in_new_tab: false,
  };
  if (location === "header" && !items.some((item) => item.url === videoRequestLink.url)) {
    items = [...items, videoRequestLink];
  }
  return items
    .filter((item) => item.location === location || item.location === "both")
    .sort((a, b) => a.order - b.order);
});

function mapCourse(course: CmsCourse): Course {
  return {
    slug: course.slug,
    title: course.title,
    level: course.academic_level,
    curriculum: course.curriculum,
    price: Number(course.price),
    lessons: course.lesson_count,
    hours: course.estimated_hours,
    description: course.short_description || course.description || "",
    outcomes: course.outcomes ?? [],
    modules: course.modules?.map((module) => module.title) ?? [],
    featured: course.featured,
  };
}

export async function getManagedCourses(): Promise<Course[]> {
  const response = await cmsFetch<Paginated<CmsCourse>>("/courses/?page_size=100");
  return response?.results?.length ? response.results.map(mapCourse) : courses;
}

export async function getManagedCourse(slug: string): Promise<Course | undefined> {
  const course = await cmsFetch<CmsCourse>(`/courses/${encodeURIComponent(slug)}/`);
  return course ? mapCourse(course) : courses.find((item) => item.slug === slug);
}
