"use client";

import { useEffect, useRef, type ReactNode } from "react";

export function HeaderNavigationControls({ children }: { children: ReactNode }) {
  const navigation = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!navigation.current) return;
    const root = navigation.current;

    const close = () => {
      root.querySelectorAll<HTMLDetailsElement>("details[open]").forEach((menu) => {
        menu.open = false;
      });
    };

    function handlePointerDown(event: PointerEvent) {
      if (event.target instanceof Node && !root.contains(event.target)) close();
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;

      const menu = document.activeElement?.closest<HTMLDetailsElement>("details[open]");
      if (menu && root.contains(menu)) {
        menu.open = false;
        menu.querySelector("summary")?.focus();
        event.preventDefault();
      } else {
        close();
      }
    }

    function handleFocusOut(event: FocusEvent) {
      if (!(event.target instanceof Element)) return;
      const group = event.target.closest<HTMLDetailsElement>(".header-group[open]");
      if (group && !(event.relatedTarget instanceof Node && group.contains(event.relatedTarget))) {
        group.open = false;
      }
    }

    const desktop = window.matchMedia("(min-width: 1280px)");
    document.addEventListener("pointerdown", handlePointerDown, { passive: true });
    document.addEventListener("keydown", handleEscape);
    root.addEventListener("focusout", handleFocusOut);
    desktop.addEventListener("change", close);

    for (const link of root.querySelectorAll<HTMLAnchorElement>("a[href]")) {
      if (link.origin === location.origin && link.pathname === location.pathname) {
        link.setAttribute("aria-current", "page");
      }
    }

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
      root.removeEventListener("focusout", handleFocusOut);
      desktop.removeEventListener("change", close);
    };
  }, []);

  return <div ref={navigation} className="header-navigation">{children}</div>;
}
