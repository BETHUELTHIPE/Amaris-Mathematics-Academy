const recoveryScript = String.raw`
(() => {
  const notice = document.getElementById("connection-recovery");
  if (!notice) return;
  const title = notice.querySelector("[data-recovery-title]");
  const message = notice.querySelector("[data-recovery-message]");
  const retry = notice.querySelector("[data-recovery-retry]");
  const close = notice.querySelector("[data-recovery-close]");
  let restorationTimer;

  const hide = () => {
    notice.hidden = true;
  };
  const showOffline = () => {
    if (restorationTimer) window.clearTimeout(restorationTimer);
    if (title) title.textContent = "Connection lost";
    if (message) message.textContent = "Keep this page open. Nothing will be submitted until you reconnect.";
    if (retry) retry.hidden = false;
    notice.hidden = false;
  };
  const showRestored = () => {
    if (title) title.textContent = "Connection restored";
    if (message) message.textContent = "You can continue where you left off.";
    if (retry) retry.hidden = true;
    notice.hidden = false;
    if (restorationTimer) window.clearTimeout(restorationTimer);
    restorationTimer = window.setTimeout(hide, 4500);
  };
  const preventOfflineSubmission = (event) => {
    if (navigator.onLine) return;
    event.preventDefault();
    showOffline();
  };

  window.addEventListener("offline", showOffline);
  window.addEventListener("online", showRestored);
  document.addEventListener("submit", preventOfflineSubmission, true);
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hide();
  });
  close?.addEventListener("click", hide);
  retry?.addEventListener("click", () => {
    if (navigator.onLine) window.location.reload();
    else showOffline();
  });
  if (!navigator.onLine) showOffline();
})();
`;

export function ConnectionRecovery() {
  return (
    <>
      <div
        id="connection-recovery"
        hidden
        className="fixed inset-x-4 bottom-4 z-[100] mx-auto max-w-2xl rounded-2xl border border-white/15 bg-[#07152d] p-4 text-white shadow-[0_24px_80px_rgba(7,21,45,.35)] sm:p-5"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        <div className="flex items-start gap-3">
          <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-xl bg-[#ffcc66]/15 font-bold text-[#ffcc66]">!</span>
          <div className="min-w-0 flex-1">
            <p className="font-bold" data-recovery-title>Connection lost</p>
            <p className="mt-1 text-sm leading-6 text-white/65" data-recovery-message>Keep this page open. Nothing will be submitted until you reconnect.</p>
            <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
              <button type="button" data-recovery-retry className="inline-flex min-h-11 cursor-pointer items-center rounded-lg font-bold text-[#ffcc66]">Try again</button>
              <a href="/connection-lost" className="inline-flex min-h-11 items-center rounded-lg font-semibold text-white/70 hover:text-white">Recovery help</a>
            </div>
          </div>
          <button type="button" data-recovery-close className="inline-flex min-h-11 cursor-pointer items-center rounded-lg px-2 text-sm font-semibold text-white/65 hover:bg-white/10 hover:text-white" aria-label="Close connection notice">Close</button>
        </div>
      </div>
      <script dangerouslySetInnerHTML={{ __html: recoveryScript }} />
    </>
  );
}
