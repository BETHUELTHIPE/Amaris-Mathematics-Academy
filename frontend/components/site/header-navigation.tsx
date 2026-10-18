import type { ReactNode } from "react";
import { ArrowUpRight, BookOpen, ChevronDown, GraduationCap, Menu, X } from "lucide-react";
import { groupNavigation, type NavigationLink } from "@/lib/navigation";

// Native <details> menus work before JavaScript. Only enhancement behaviours
// (Escape, outside click, breakpoint close) need this tiny script; the header
// itself stays a Server Component and requires no React navigation hydration.
const enhanceNavigation = String.raw`
(() => {
  const root = document.currentScript?.previousElementSibling;
  if (!(root instanceof HTMLElement) || !root.classList.contains("header-navigation")) return;
  const close = () => root.querySelectorAll("details[open]").forEach(menu => { menu.open = false; });
  document.addEventListener("pointerdown", event => {
    if (!root.contains(event.target)) close();
  }, { passive: true });
  document.addEventListener("keydown", event => {
    if (event.key !== "Escape") return;
    const menu = document.activeElement?.closest("details[open]");
    if (menu && root.contains(menu)) {
      menu.open = false;
      menu.querySelector("summary")?.focus();
      event.preventDefault();
    } else {
      close();
    }
  });
  root.addEventListener("focusout", event => {
    const group = event.target?.closest(".header-group[open]");
    if (!group) return;
    queueMicrotask(() => {
      if (!group.contains(document.activeElement)) group.open = false;
    });
  });
  window.matchMedia("(min-width: 1280px)").addEventListener("change", close);
  for (const link of root.querySelectorAll("a[href]")) {
    if (link.origin === location.origin && link.pathname === location.pathname) {
      link.setAttribute("aria-current", "page");
    }
  }
})();
`;

export function HeaderNavigation({ links, desktopAccount, mobileAccount }: {
  links: NavigationLink[];
  desktopAccount: ReactNode;
  mobileAccount: ReactNode;
}) {
  const { groups, featured } = groupNavigation(links);
  const linkProps = (link: NavigationLink) => ({
    href: link.url,
    target: link.open_in_new_tab ? "_blank" : undefined,
    rel: link.open_in_new_tab ? "noopener noreferrer" : undefined,
  });

  const groupMenus = (mobile: boolean) => groups.filter(group => group.links.length > 0).map(group => (
    <details key={group.id} className={mobile ? "header-mobile-group" : "header-group"} name={mobile ? "mobile-navigation-groups" : "desktop-navigation-groups"}>
      <summary className="header-group-trigger">{group.label}<ChevronDown aria-hidden="true" size={14} className="header-chevron" /></summary>
      <div className={mobile ? "header-mobile-links" : "header-dropdown"}>
        {!mobile && <p className="header-dropdown-caption">{group.description}</p>}
        {group.links.map(link => <a key={link.url} {...linkProps(link)} className="header-menu-link">
          <span><span className="header-link-label">{link.label}</span>{!mobile && <span className="header-link-description">{link.description}</span>}</span>
          <ArrowUpRight size={15} aria-hidden="true" />
        </a>)}
      </div>
    </details>
  ));

  return <><div className="header-navigation">
    <nav aria-label="Main navigation" className="header-desktop-nav">
      {groupMenus(false).slice(0, 1)}
      {featured.map(link => <a key={link.url} {...linkProps(link)} className="header-featured"><GraduationCap size={17} aria-hidden="true" />{link.label}</a>)}
      {groupMenus(false).slice(1)}
    </nav>
    <div className="header-desktop-account">{desktopAccount}</div>
    <details className="header-mobile-menu">
      <summary className="header-mobile-trigger"><Menu size={20} className="header-menu-icon" aria-hidden="true" /><X size={20} className="header-close-icon" aria-hidden="true" /><span>Menu</span></summary>
      <div className="header-mobile-panel">
        <nav aria-label="Mobile navigation">
          <p className="header-mobile-caption"><BookOpen size={15} aria-hidden="true" /> Your next step starts here</p>
          {featured.map(link => <a key={link.url} {...linkProps(link)} className="header-featured header-mobile-featured"><GraduationCap size={21} aria-hidden="true" /><span>{link.label}<small>A fresh start. A stronger future.</small></span><ArrowUpRight size={17} aria-hidden="true" /></a>)}
          {groupMenus(true)}
        </nav>
        <div className="header-mobile-account">{mobileAccount}</div>
      </div>
    </details>
  </div><script dangerouslySetInnerHTML={{ __html: enhanceNavigation }} /></>;
}
