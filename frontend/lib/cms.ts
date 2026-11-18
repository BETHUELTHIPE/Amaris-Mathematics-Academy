import { cache } from "react";
import { academyBrand, type AcademyBrand } from "@/lib/brand";
import { courses, type Course } from "@/lib/courses";
import { prepareAnnouncements } from "@/lib/announcements";
import { normalizeCmsApiBaseUrl } from "@/lib/cms-api-url";
import { COURSE_PAGE_SIZE, catalogueApiPath, normalizeCatalogOptions } from "@/lib/course-catalog-search.mjs";

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

const configuredCmsUrl = process.env.CMS_API_URL;
let cmsBaseUrl: string | undefined;
try {
  cmsBaseUrl = configuredCmsUrl ? normalizeCmsApiBaseUrl(configuredCmsUrl) : undefined;
} catch {
  cmsBaseUrl = undefined;
}

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
  { label: "Matric Upgrades", url: "/matric-upgrades", location: "both", order: 35, open_in_new_tab: false },
  { label: "AI Software Developer", url: "/ai-software-developer", location: "both", order: 36, open_in_new_tab: false },
  { label: "About", url: "/about", location: "both", order: 40, open_in_new_tab: false },
  { label: "Announcements", url: "/announcements", location: "both", order: 42, open_in_new_tab: false },
  { label: "Request a topic video", url: "/request-a-video", location: "both", order: 44, open_in_new_tab: false },
  { label: "Book online live class", url: "/book-online-live-class", location: "both", order: 45, open_in_new_tab: false },
  { label: "Become a tutor", url: "/tutor/apply", location: "both", order: 47, open_in_new_tab: false },
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
          label: requiredItem.url === "/request-a-video" ? requiredItem.label : managedItem.label,
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

export type CourseCatalogOptions = {
  query?: string;
  programme?: string;
  level?: string;
  sort?: string;
  page?: number;
};

export type CourseCatalog = {
  courses: Course[];
  count: number;
  page: number;
  pageSize: number;
  hasNext: boolean;
  hasPrevious: boolean;
  available: boolean;
  validationError: string;
};

export async function getManagedCourseCatalog(options: CourseCatalogOptions = {}): Promise<CourseCatalog> {
  const safe = normalizeCatalogOptions(options);
  const empty: CourseCatalog = {
    courses: [], count: 0, page: safe.page, pageSize: COURSE_PAGE_SIZE,
    hasNext: false, hasPrevious: false, available: false, validationError: safe.validationError,
  };
  if (safe.validationError || !cmsBaseUrl) return empty;
  const response = await cmsFetch<Paginated<CmsCourse>>(catalogueApiPath(safe));
  if (!response || !Array.isArray(response.results) || !Number.isSafeInteger(response.count) || response.count < 0) return empty;
  return {
    ...empty, courses: response.results.map(mapCourse), count: response.count,
    hasNext: Boolean(response.next), hasPrevious: Boolean(response.previous), available: true,
  };
}

export async function getManagedCourses(): Promise<Course[]> {
  return (await getManagedCourseCatalog()).courses;
}

export async function getManagedFeaturedCourses(): Promise<Course[]> {
  const response = await cmsFetch<CmsCourse[]>("/courses/featured/");
  return Array.isArray(response) ? response.map(mapCourse) : [];
}

export async function getManagedAnnouncements() {
  const response = await cmsFetch<unknown>("/announcements/");
  return prepareAnnouncements(response);
}

export async function getManagedCourse(slug: string): Promise<Course | undefined> {
  const course = await cmsFetch<CmsCourse>(`/courses/${encodeURIComponent(slug)}/`);
  return course ? mapCourse(course) : configuredCmsUrl ? undefined : courses.find((item) => item.slug === slug);
}

