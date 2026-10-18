/* Progressive enhancement for public site sharing.
 * No React runtime, account details, current pathname or search parameters.
 */
(() => {
  if (window.__amarisShareInstalled) return;
  window.__amarisShareInstalled = true;

  const SHARE_TITLE = "Amaris Mathematics Academy";
  const SHARE_MESSAGE = "Explore Amaris Mathematics Academy for CAPS, IEB, TVET and university learning support.";

  function showStatus(root, message, label) {
    const status = root.querySelector("[data-share-status]");
    const button = root.querySelector("[data-share-trigger]");
    const title = root.querySelector("[data-share-label]");
    if (status) status.textContent = message;
    if (title) title.textContent = label;
    if (button) button.setAttribute("aria-label", label);
  }
  function showManual(root, url) {
    const container = root.querySelector("[data-share-manual]");
    const input = root.querySelector("[data-share-url]");
    if (container) container.hidden = false;
    if (input) {
      input.value = url;
      requestAnimationFrame(() => {
        input.focus();
        input.select();
      });
    }
    showStatus(root, "Select and copy the website link below.", "Share website");
  }

  document.addEventListener("click", async (event) => {
    const button = event.target instanceof Element
      ? event.target.closest("[data-share-trigger]")
      : null;
    if (!button) return;
    const root = button.closest("[data-share-website]");
    if (!root || button.disabled) return;
    const url = new URL("/", window.location.origin).toString();
    button.disabled = true;
    showStatus(root, "", "Share website");
    const fallback = root.querySelector("[data-share-manual]");
    if (fallback) fallback.hidden = true;
    try {
      if (typeof navigator.share === "function") {
        try {
          await navigator.share({ title: SHARE_TITLE, text: SHARE_MESSAGE, url });
          return;
        } catch (error) {
          if (error?.name === "AbortError") return;
        }
      }
      try {
        if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
        await navigator.clipboard.writeText(url);
        showStatus(root, "Amaris website link copied to clipboard.", "Link copied!");
      } catch {
        showManual(root, url);
      }
    } finally {
      button.disabled = false;
    }
  });
})();
