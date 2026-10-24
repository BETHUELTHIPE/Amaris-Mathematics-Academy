export const contactRequiredMessages = {
  fullName: "Please enter your full name.",
  email: "Please enter your email address.",
  phone: "Please enter your phone number.",
  country: "Please choose your country.",
  province: "Please choose your province or region.",
  city: "Please choose your city or town.",
  enquiryType: "Please choose an enquiry type.",
  message: "Please enter your message.",
  consent: "Please agree so we can respond to your enquiry.",
} as const;

export type ContactField = keyof typeof contactRequiredMessages;

export function contactRequiredErrors(values: Record<string, unknown>): Partial<Record<ContactField, string>> {
  const errors: Partial<Record<ContactField, string>> = {};
  for (const field of Object.keys(contactRequiredMessages) as ContactField[]) {
    const value = values[field];
    if (field === "consent" ? value !== "on" : typeof value !== "string" || !value.trim()) {
      errors[field] = contactRequiredMessages[field];
    }
  }
  return errors;
}
