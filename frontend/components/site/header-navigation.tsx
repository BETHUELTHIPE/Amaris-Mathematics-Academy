"use client";
import { useEffect, useRef, useSyncExternalStore, type ReactNode } from "react";
import { ArrowUpRight, BookOpen, ChevronDown, GraduationCap, Menu, X } from "lucide-react";
import { groupNavigation, type NavigationLink } from "@/lib/navigation";

const getPathname = () => window.location.pathname;
const getServerPathname = () => "";
const subscribeToLocation = (notify: () => void) => {
  window.addEventListener("popstate", notify);
  return () => window.removeEventListener("popstate", notify);
};

export function HeaderNavigation({ links, desktopAccount, mobileAccount }: {
  links: NavigationLink[];
  desktopAccount: ReactNode;
  mobileAccount: ReactNode;
}) {
  const root = useRef<HTMLDivElement>(null);
  const pathname = useSyncExternalStore(subscribeToLocation, getPathname, getServerPathname);
  const { groups, featured } = groupNavigation(links);

  useEffect(() => {
    const close = () => {
      root.current?.querySelectorAll<HTMLDetailsElement>("details[open]").forEach(details => {
        details.open = false;
      });
    };
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) close();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const focused = document.activeElement;
      const details = focused?.closest("details[open]") as HTMLDetailsElement | null;
      if (details && root.current?.contains(details)) {
        details.open = false;
        details.querySelector<HTMLElement>("summary")?.focus();
        event.preventDefault();
      } else close();
    };
    const resize = () => close();
    const query = window.matchMedia("(min-width: 1280px)");
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    query.addEventListener("change", resize);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
      query.removeEventListener("change", resize);
    };
  }, []);

  const onToggle = (event: React.SyntheticEvent<HTMLDetailsElement>) => {
    const current = event.currentTarget;
    if (!current.open) return;
    // Keep a mobile group's parent disclosure open while closing sibling groups.
    root.current?.querySelectorAll<HTMLDetailsElement>("details[open]").forEach(details => {
      if (details !== current && !details.contains(current) && !current.contains(details)) details.open = false;
    });
  };
  const linkProps = (link: NavigationLink) => ({
    href: link.url,
    target: link.open_in_new_tab ? "_blank" : undefined,
    rel: link.open_in_new_tab ? "noopener noreferrer" : undefined,
    "aria-current": pathname === link.url ? "page" as const : undefined,
  });

  const groupMenus = (mobile: boolean) => groups.filter(group => group.links.length > 0).map(group => (
    <details key={group.id} className={mobile ? "header-mobile-group" : "header-group"} name={mobile ? "mobile-navigation-groups" : "desktop-navigation-groups"} onToggle={onToggle}
      onBlur={event => {
        if (!mobile && event.relatedTarget && !event.currentTarget.contains(event.relatedTarget as Node)) event.currentTarget.open = false;
      }}>
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

  return <div ref={root} className="header-navigation">
    <nav aria-label="Main navigation" className="header-desktop-nav">
      {groupMenus(false).slice(0, 1)}
      {featured.map(link => <a key={link.url} {...linkProps(link)} className="header-featured"><GraduationCap size={17} aria-hidden="true" />{link.label}</a>)}
      {groupMenus(false).slice(1)}
    </nav>
    <div className="header-desktop-account">{desktopAccount}</div>
    <details className="header-mobile-menu" onToggle={onToggle}>
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
  </div>;
}
