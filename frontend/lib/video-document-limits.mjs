export const MAX_VIDEO_DOCUMENT_BYTES = 1024 * 1024 * 1024;
export const MAX_VIDEO_DOCUMENTS = 5;
// Allow bounded multipart fields and separators in addition to the file quota.
export const MAX_VIDEO_UPLOAD_BODY_BYTES = MAX_VIDEO_DOCUMENT_BYTES + 1024 * 1024;

export function validateVideoDocuments(files) {
  if (files.length > MAX_VIDEO_DOCUMENTS) return "Upload no more than five supporting documents.";
  if (files.some(file => file.size <= 0 || file.size > MAX_VIDEO_DOCUMENT_BYTES)) {
    return "Each document must be non-empty and no larger than 1 GB.";
  }
  if (files.reduce((total, file) => total + file.size, 0) > MAX_VIDEO_DOCUMENT_BYTES) {
    return "Supporting documents must total no more than 1 GB.";
  }
  if (files.some(file => !["application/pdf", "image/jpeg", "image/png"].includes(file.type))) {
    return "Supporting documents must be PDF, JPEG or PNG files.";
  }
  return "";
}

/** Forward with backpressure; never parse or buffer a 1 GB FormData in Node. */
export function boundedVideoUpload(source) {
  const state = { exceeded: false, body: null };
  let bytes = 0;
  state.body = source.pipeThrough(new TransformStream({
    transform(chunk, controller) {
      bytes += chunk.byteLength;
      if (bytes > MAX_VIDEO_UPLOAD_BODY_BYTES) {
        state.exceeded = true;
        throw new RangeError("Supporting documents must total no more than 1 GB.");
      }
      controller.enqueue(chunk);
    },
  }));
  return state;
}
