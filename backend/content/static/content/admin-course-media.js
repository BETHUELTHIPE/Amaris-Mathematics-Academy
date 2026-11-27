(() => {
  const chunkSize = 16 * 1024 * 1024;
  const protocol = "1.0.0";

  async function tusOffset(url) {
    const response = await fetch(url, { method: "HEAD", headers: { "Tus-Resumable": protocol }, cache: "no-store" });
    const header = response.headers.get("Upload-Offset");
    const offset = Number(header);
    if (!response.ok || header === null || !Number.isSafeInteger(offset) || offset < 0) {
      throw new Error("Vimeo did not confirm the upload position.");
    }
    return offset;
  }

  async function sendVimeo(url, file, progress) {
    let offset = await tusOffset(url);
    let retries = 0;
    while (offset < file.size) {
      const end = Math.min(file.size, offset + chunkSize);
      try {
        const response = await fetch(url, {
          method: "PATCH",
          headers: { "Tus-Resumable": protocol, "Upload-Offset": String(offset),
            "Content-Type": "application/offset+octet-stream" },
          body: file.slice(offset, end),
        });
        if (!response.ok || Number(response.headers.get("Upload-Offset")) !== end) {
          throw new Error("Vimeo did not acknowledge the uploaded chunk.");
        }
        retries = 0;
        offset = end;
        progress(offset / file.size);
      } catch (error) {
        if (++retries > 3) throw error;
        await new Promise((resolve) => setTimeout(resolve, retries * 800));
        offset = await tusOffset(url);
      }
    }
    if (offset !== file.size) throw new Error("Vimeo reported an unexpected file size.");
  }

  function sendS3(url, headers, file, progress) {
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open("PUT", url);
      for (const [name, value] of Object.entries(headers)) request.setRequestHeader(name, value);
      request.upload.onprogress = (event) => {
        if (event.lengthComputable) progress(event.loaded / event.total);
      };
      request.onload = () => request.status === 200
        ? resolve() : reject(new Error("AWS S3 rejected the upload. Try again."));
      request.onerror = () => reject(new Error("The connection to AWS S3 was interrupted."));
      request.send(file);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const controls = document.querySelector("[data-academy-upload]");
    if (!controls) return;
    const form = controls.closest("form");
    const provider = form.elements.provider;
    const ticket = form.elements.upload_ticket;
    const input = controls.querySelector("input[type=file]");
    const button = controls.querySelector("[data-upload-start]");
    const status = controls.querySelector("[data-upload-status]");
    const meter = controls.querySelector("progress");
    let upload = null;
    let busy = false;

    function refresh() {
      const destination = provider.value;
      const enabled = controls.dataset[destination] === "yes";
      button.disabled = busy || !enabled;
      input.disabled = busy || !enabled;
      if (!enabled) status.textContent = destination === "youtube"
        ? "For YouTube, enter the video ID or URL in the section below."
        : "This provider is not configured on this server.";
      else if (!busy) status.textContent = ticket.value ? "File received. Save this video record." : "";
    }

    for (const element of [provider, input]) element.addEventListener("change", () => {
      upload = null;
      ticket.value = "";
      meter.hidden = true;
      refresh();
    });

    form.addEventListener("submit", (event) => {
      if (busy) {
        event.preventDefault();
        status.textContent = "Wait for the upload to finish before saving.";
      }
    });

    button.addEventListener("click", async () => {
      const file = input.files[0];
      const destination = provider.value;
      const title = form.elements.title.value.trim();
      if (!file || !title) {
        status.textContent = "Enter a video title and select a video file.";
        return;
      }
      busy = true;
      refresh();
      provider.disabled = true;
      meter.hidden = false;
      status.textContent = "Uploading…";
      try {
        if (!upload) {
          const response = await fetch(controls.dataset.url, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": form.elements.csrfmiddlewaretoken.value },
            body: JSON.stringify({ provider: destination, asset: controls.dataset.asset,
              filename: file.name, size: file.size, title }),
          });
          const body = await response.json();
          if (!response.ok) throw new Error(body.error || "The server could not start the upload.");
          upload = body;
        }
        const progress = (fraction) => { meter.value = 100 * fraction; };
        if (destination === "s3") await sendS3(upload.url, upload.headers, file, progress);
        else await sendVimeo(upload.url, file, progress);
        progress(1);
        ticket.value = upload.ticket;
        status.textContent = "File received. Save this video record.";
      } catch (error) {
        if (destination === "s3") upload = null;
        status.textContent = error.message || "The upload was interrupted. Try again.";
      } finally {
        busy = false;
        provider.disabled = false;
        button.disabled = false;
        input.disabled = false;
      }
    });
    refresh();
  });
})();
