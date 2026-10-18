/* This public catalogue is server-rendered, including every course link.
 * Optional, delegated enhancement: no React runtime or Next.js client router.
 * A disconnected/offline/no-JavaScript browser still sees all the courses.
 */
(() => {
  function initialize(root) {
    if (root.dataset.courseEnhanced === "true") return;
    root.dataset.courseEnhanced = "true";
    let selectedFilter = "All";
    const query = root.querySelector("[data-course-query]");
    const cards = [...root.querySelectorAll("[data-course-card]")];
    const empty = root.querySelector("[data-course-empty]");
    const buttons = [...root.querySelectorAll("[data-course-filter]")];

    const apply = () => {
      const needle = (query?.value || "").trim().toLocaleLowerCase();
      let visible = 0;
      for (const card of cards) {
        const level = card.dataset.courseLevel || "";
        const curriculum = card.dataset.courseCurriculum || "";
        const matchesText = (card.dataset.courseSearch || "").includes(needle);
        const matchesFilter = selectedFilter === "All"
          || (selectedFilter === "TVET" ? level.includes("TVET")
              : selectedFilter === "University" ? level === "University"
              : curriculum.includes(selectedFilter));
        const shown = matchesText && matchesFilter;
        card.hidden = !shown;
        // Prevent a Tailwind display utility from defeating the hidden attribute.
        card.style.display = shown ? "" : "none";
        if (shown) visible++;
      }
      if (empty) empty.hidden = visible !== 0;
    };
    for (const button of buttons) {
      button.addEventListener("click", () => {
        selectedFilter = button.dataset.courseFilter || "All";
        for (const option of buttons) {
          const active = option === button;
          option.setAttribute("aria-pressed", String(active));
          option.classList.toggle("bg-[#0b2a5b]", active);
          option.classList.toggle("text-white", active);
          option.classList.toggle("bg-[#edf2f8]", !active);
          option.classList.toggle("text-[#38465e]", !active);
          option.classList.toggle("hover:bg-[#dfe8f3]", !active);
        }
        apply();
      });
    }
    query?.addEventListener("input", apply);
    apply();
  }

  const init = () => document.querySelectorAll("[data-course-browser]").forEach(initialize);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
