/* Amaris Admin progressive enhancement. No form values are inspected, stored,
   logged, transmitted, or modified. Native Django form handling is preserved. */
(function () {
  "use strict";

  function init() {
    // Jazzmin uses standard Django change forms, but can also display dialogs.
    // Only show a non-blocking progress cue for actual admin save forms.
    const forms = document.querySelectorAll("form[id$='_form']");
    for (const form of forms) {
      const saveButton = form.querySelector(
        'input[name="_save"], button[name="_save"], input[type="submit"], button[type="submit"]'
      );
      if (!saveButton || form.dataset.amarisSaveFeedback === "ready") {
        continue;
      }
      form.dataset.amarisSaveFeedback = "ready";
      form.addEventListener("submit", function (event) {
        if (event.defaultPrevented || !form.checkValidity()) return;
        // Jazzmin may use a custom form-group instead of Django's .submit-row.
        // Place the cue beside the actual save control in either template.
        const actions = form.querySelector(".submit-row") || saveButton.parentElement;
        if (!actions || actions.querySelector(".amaris-admin-submit-status")) return;

        const status = document.createElement("span");
        status.className = "amaris-admin-submit-status";
        status.setAttribute("role", "status");
        status.setAttribute("aria-live", "polite");
        status.textContent = "Submitting changes…";
        actions.appendChild(status);
        // The browser and Django remain responsible for whether save succeeds.
        // Never disable buttons: invalid or rejected saves must remain retryable.
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }

  // A back-forward restored form must not show an obsolete submitting cue.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) return;
    document.querySelectorAll(".amaris-admin-submit-status").forEach(function (node) {
      node.remove();
    });
  });
})();
