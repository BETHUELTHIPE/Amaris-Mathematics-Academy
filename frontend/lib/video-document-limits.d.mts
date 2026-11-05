export const MAX_VIDEO_DOCUMENT_BYTES: number;
export const MAX_VIDEO_DOCUMENTS: number;
export const MAX_VIDEO_UPLOAD_BODY_BYTES: number;
export function validateVideoDocuments(files: readonly { size: number; type: string }[]): string;
export function boundedVideoUpload(source: ReadableStream<Uint8Array>): {
  exceeded: boolean;
  body: ReadableStream<Uint8Array>;
};
