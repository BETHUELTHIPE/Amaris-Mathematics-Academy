/* Native <details> navigation is usable without JavaScript.
 * This optional enhancement preserves close-on-Escape, outside click and
 * breakpoint behaviour with no React navigation hydration.
 */
(() => {
  const init = () => {
    for (const root of document.querySelectorAll(".header-navigation")) {
      if (root.dataset.enhanced === "true") continue;
      root.dataset.enhanced = "true";
      const close = () => root.querySelectorAll("details[open]").forEach(d => { d.open = false; });
      document.addEventListener("pointerdown", event => {
        if (!root.contains(event.target)) close();
      }, { passive: true });
      document.addEventListener("keydown", event => {
        if (event.key !== "Escape") return;
        const target = document.activeElement?.closest("details[open]");
        if (target && root.contains(target)) {
          target.open = false;
          target.querySelector("summary")?.focus();
          event.preventDefault();
        } else close();
      });
      root.addEventListener("focusout", event => {
        const group = event.target?.closest(".header-group[open]");
        if (!group) return;
        queueMicrotask(() => { if (!group.contains(document.activeElement)) group.open = false; });
      });
      window.matchMedia("(min-width: 1280px)").addEventListener("change", close);
      for (const link of root.querySelectorAll("a[href]")) {
        if (link.origin === location.origin && link.pathname === location.pathname) {
          link.setAttribute("aria-current", "page");
        }
      }
    }
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
