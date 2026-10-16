export type NavigationLink = {
  label: string;
  url: string;
  open_in_new_tab: boolean;
};

export const navigationGroups = [
  { id: "learn", label: "Learn", description: "Find your next step", urls: ["/courses", "/how-it-works", "/pricing", "/book-online-live-class"] },
  { id: "resources", label: "Resources", description: "Stay informed. Keep learning.", urls: ["/announcements", "/request-a-video"] },
  { id: "academy", label: "Academy", description: "Meet Amaris and get in touch", urls: ["/about", "/tutor/apply", "/contact", "/tutor/login"] },
] as const;

const descriptions: Record<string, string> = {
  "/courses": "Explore our mathematics programmes",
  "/how-it-works": "See how learning at Amaris works",
  "/pricing": "Plan your learning investment",
  "/book-online-live-class": "Find and book your next live lesson",
  "/announcements": "The latest news from the academy",
  "/request-a-video": "Tell us which topic you need help with",
  "/about": "Our purpose, approach and story",
  "/tutor/apply": "Share your expertise with our learners",
  "/contact": "Talk to our team about your goals",
  "/tutor/login": "Access your tutor workspace",
};

export function groupNavigation(links: NavigationLink[]) {
  const groupedUrls = new Set<string>(navigationGroups.flatMap(group => [...group.urls]));
  const allLinks = links.some(link => link.url === "/tutor/login")
    ? links
    : [...links, { label: "Tutor portal", url: "/tutor/login", open_in_new_tab: false }];
  return {
    featured: links.filter(link => link.url === "/matric-upgrades"),
    groups: navigationGroups.map(group => ({
      ...group,
      links: allLinks.filter(link => (group.urls as readonly string[]).includes(link.url) ||
        (group.id === "resources" && link.url !== "/matric-upgrades" && !groupedUrls.has(link.url)))
        .map(link => ({ ...link, description: descriptions[link.url] ?? "Explore more from Amaris" })),
    })),
  };
}
