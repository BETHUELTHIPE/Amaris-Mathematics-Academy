(() => {
  const navigation = ".header-navigation";
  const closeMenus = () => {
    document.querySelectorAll(`${navigation} details[open]`).forEach((menu) => {
      menu.open = false;
    });
  };

  document.addEventListener("pointerdown", (event) => {
    if (event.target instanceof Element && !event.target.closest(navigation)) {
      closeMenus();
    }
  }, { passive: true, capture: true });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;

    const menu = document.activeElement?.closest(`${navigation} details[open]`);
    if (menu) {
      menu.open = false;
      menu.querySelector("summary")?.focus();
      event.preventDefault();
    } else {
      closeMenus();
    }
  }, { capture: true });

  document.addEventListener("focusout", (event) => {
    if (!(event.target instanceof Element)) return;
    const group = event.target.closest(`${navigation} details.header-group[open]`);
    if (group && !(event.relatedTarget instanceof Node && group.contains(event.relatedTarget))) {
      group.open = false;
    }
  });

  window.matchMedia("(min-width: 1280px)").addEventListener("change", closeMenus);

  for (const link of document.querySelectorAll(`${navigation} a[href]`)) {
    if (link.origin === location.origin && link.pathname === location.pathname) {
      link.setAttribute("aria-current", "page");
    }
  }

  document.documentElement.dataset.amarisHeaderControls = "ready";
})();
