/** Required identity and qualification uploads for tutor recruitment.
 * Documents remain private and must never appear in acknowledgement emails.
 */
export const REQUIRED_TUTOR_DOCUMENTS = [
  { name: "document_id", label: "Upload ID", description: "A readable copy of your identity document" },
  { name: "document_cv", label: "Upload CV", description: "Your current curriculum vitae" },
  { name: "document_matric", label: "Upload Matric certificate", description: "Your Matric or equivalent school-leaving certificate" },
  { name: "document_academic", label: "Upload Academic records", description: "Your academic transcript or statement of results" },
  { name: "document_tertiary", label: "Upload Tertiary Certificate", description: "Your tertiary qualification certificate" },
  { name: "document_other", label: "Upload other document", description: "One additional supporting document relevant to your application" },
] as const;

export const MAX_TUTOR_DOCUMENT_BYTES = 5 * 1024 * 1024;
export const MAX_TUTOR_DOCUMENTS_TOTAL_BYTES = 30 * 1024 * 1024;
const allowedTypes = new Set(["application/pdf", "image/jpeg", "image/png"]);

export function validateRequiredTutorDocuments(data: FormData): Record<string, string[]> {
  const errors: Record<string, string[]> = {};
  let total = 0;

  for (const { name, label } of REQUIRED_TUTOR_DOCUMENTS) {
    const files = data.getAll(name);
    if (files.length !== 1 || !(files[0] instanceof File) || files[0].size === 0) {
      errors[name] = [`${label} is compulsory. Choose one file.`];
      continue;
    }
    const file = files[0];
    if (file.size > MAX_TUTOR_DOCUMENT_BYTES) {
      errors[name] = ["Maximum 5 MB per file."];
    } else if (!allowedTypes.has(file.type.toLowerCase())) {
      errors[name] = ["Upload a PDF, JPEG or PNG file."];
    }
    total += file.size;
  }

  if (data.getAll("documents").some(file => file instanceof File && file.size > 0)) {
    errors.documents = ["Use the six separate mandatory upload fields."];
  }
  if (total > MAX_TUTOR_DOCUMENTS_TOTAL_BYTES) {
    errors.documents = ["The six uploaded files may total no more than 30 MB."];
  }
  return errors;
}
