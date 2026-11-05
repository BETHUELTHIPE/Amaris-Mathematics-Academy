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

type Paginated<T> = { count: number; next: string | null; previous: string | null; results: T[] };
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

const requiredPublicNavigation: CmsNavigationItem[] = [
  { label: "Courses", url: "/courses", location: "both", order: 10, open_in_new_tab: false },
  { label: "How it works", url: "/how-it-works", location: "both", order: 20, open_in_new_tab: false },
  { label: "Pricing", url: "/pricing", location: "both", order: 30, open_in_new_tab: false },
  { label: "About", url: "/about", location: "both", order: 40, open_in_new_tab: false },
  { label: "Book online live class", url: "/book-online-live-class", location: "both", order: 45, open_in_new_tab: false },
  { label: "Announcements", url: "/announcements", location: "both", order: 48, open_in_new_tab: false },
  { label: "Contact", url: "/contact", location: "both", order: 50, open_in_new_tab: false },
];

function mergeRequiredNavigation(
  managedItems: CmsNavigationItem[] | null | undefined,
): CmsNavigationItem[] {
  if (!managedItems?.length) return requiredPublicNavigation;

  const managedByUrl = new Map(managedItems.map((item) => [item.url, item]));
  const requiredUrls = new Set(requiredPublicNavigation.map((item) => item.url));
  const requiredItems = requiredPublicNavigation.map((requiredItem) => {
    const managedItem = managedByUrl.get(requiredItem.url);
    return managedItem
      ? {
          ...requiredItem,
          ...managedItem,
          order: requiredItem.order,
          location: "both" as const,
        }
      : requiredItem;
  });
  const customItems = managedItems.filter((item) => !requiredUrls.has(item.url));
  return [...requiredItems, ...customItems];
}

function keepBookingNextToContact(items: CmsNavigationItem[]): CmsNavigationItem[] {
  const bookingIndex = items.findIndex((item) => item.url === "/book-online-live-class");
  const contactIndex = items.findIndex((item) => item.url === "/contact");
  if (bookingIndex < 0 || contactIndex < 0 || bookingIndex === contactIndex - 1) {
    return items;
  }

  const bookingItem = items[bookingIndex];
  const withoutBooking = items.filter((_, index) => index !== bookingIndex);
  const newContactIndex = withoutBooking.findIndex((item) => item.url === "/contact");
  return [
    ...withoutBooking.slice(0, newContactIndex),
    bookingItem,
    ...withoutBooking.slice(newContactIndex),
  ];
}

export const getManagedNavigation = cache(async (location: "header" | "footer") => {
  const managedItems = (await getManagedBootstrap())?.navigation;
  const items = mergeRequiredNavigation(managedItems)
    .filter((item) => item.location === location || item.location === "both")
    .sort((a, b) => a.order - b.order);
  return keepBookingNextToContact(items);
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

export type CourseCatalog = {
  courses: Course[];
  count: number;
  page: number;
  pageSize: number;
  hasNext: boolean;
  hasPrevious: boolean;
  available: boolean;
};

export type CourseCatalogOptions = {
  page?: number;
  query?: string;
  programme?: string;
};

// A single bounded API page prevents a 500+ course catalogue from being
// downloaded and filtered in the student's browser.
const COURSE_PAGE_SIZE = 24;

export async function getManagedCourseCatalog({
  page = 1,
  query = "",
  programme = "",
}: CourseCatalogOptions = {}): Promise<CourseCatalog> {
  const safePage = Number.isSafeInteger(page) && page > 0 ? page : 1;
  const safeQuery = query.trim().slice(0, 100);
  const safeProgramme = ["CAPS", "TVET", "University"].includes(programme) ? programme : "";
  const params = new URLSearchParams({ page: String(safePage), page_size: String(COURSE_PAGE_SIZE) });
  if (safeQuery) params.set("search", safeQuery);
  if (safeProgramme) params.set("programme", safeProgramme);

  // Preserve local/demo builds without a CMS backend. When a configured CMS
  // fails, do not pretend sample courses are real products for sale.
  if (!cmsBaseUrl) {
    const filtered = courses.filter((course) => {
      const text = `${course.title} ${course.description} ${course.curriculum} ${course.level}`.toLowerCase();
      const matchText = !safeQuery || text.includes(safeQuery.toLowerCase());
      const matchProgramme = !safeProgramme || (
        safeProgramme === "CAPS" ? course.curriculum.includes("CAPS") :
        safeProgramme === "TVET" ? (course.level.includes("TVET") || course.curriculum.includes("NATED")) :
        (course.level === "University" || course.curriculum === "Higher Education")
      );
      return matchText && matchProgramme;
    });
    const start = (safePage - 1) * COURSE_PAGE_SIZE;
    return {
      courses: filtered.slice(start, start + COURSE_PAGE_SIZE),
      count: filtered.length,
      page: safePage,
      pageSize: COURSE_PAGE_SIZE,
      hasNext: start + COURSE_PAGE_SIZE < filtered.length,
      hasPrevious: safePage > 1,
      available: true,
    };
  }

  const response = await cmsFetch<Paginated<CmsCourse>>(`/courses/?${params.toString()}`);
  if (!response || !Array.isArray(response.results) || typeof response.count !== "number") {
    return {
      courses: [], count: 0, page: safePage, pageSize: COURSE_PAGE_SIZE,
      hasNext: false, hasPrevious: false, available: false,
    };
  }
  return {
    courses: response.results.map(mapCourse),
    count: response.count,
    page: safePage,
    pageSize: COURSE_PAGE_SIZE,
    hasNext: Boolean(response.next),
    hasPrevious: Boolean(response.previous),
    available: true,
  };
}

export async function getManagedFeaturedCourses(): Promise<Course[]> {
  if (!cmsBaseUrl) return courses.filter((item) => item.featured);
  const response = await cmsFetch<CmsCourse[]>("/courses/featured/");
  return Array.isArray(response) ? response.map(mapCourse) : [];
}

// Retained for existing callers; always returns just the first page.
export async function getManagedCourses(): Promise<Course[]> {
  return (await getManagedCourseCatalog()).courses;
}

export async function getManagedCourse(slug: string): Promise<Course | undefined> {
  const course = await cmsFetch<CmsCourse>(`/courses/${encodeURIComponent(slug)}/`);
  return course ? mapCourse(course) : courses.find((item) => item.slug === slug);
}
