(() => {
  "use strict";
  const menu = document.querySelector('[data-widget="pushmenu"]');
  if (menu) {
    menu.setAttribute("aria-label", "Toggle navigation");
    menu.addEventListener("keydown", event => {
      if (event.key === " ") {
        event.preventDefault();
        menu.click();
      }
    });
  }
  document.querySelectorAll('.form-inline button[type="submit"]').forEach(button => {
    if (!button.getAttribute("aria-label")) button.setAttribute("aria-label", "Search courses");
  });
  const search = document.querySelector("[data-tool-search]");
  if (!search) return;
  search.hidden = false;
  const input = search.querySelector("input");
  const groups = [...document.querySelectorAll("[data-tool-group]")];
  const status = document.getElementById("academy-tool-status");
  const empty = document.querySelector("[data-tool-empty]");
  input.addEventListener("input", () => {
    const query = input.value.trim().toLocaleLowerCase();
    let count = 0;
    groups.forEach(group => {
      let groupCount = 0;
      group.querySelectorAll("[data-tool-name]").forEach(tool => {
        const matches = tool.dataset.toolName.toLocaleLowerCase().includes(query);
        tool.hidden = !matches;
        if (matches) groupCount += 1;
      });
      group.hidden = groupCount === 0;
      count += groupCount;
    });
    status.textContent = `${count} management ${count === 1 ? "tool" : "tools"} found.`;
    empty.hidden = count !== 0;
  });
})();
