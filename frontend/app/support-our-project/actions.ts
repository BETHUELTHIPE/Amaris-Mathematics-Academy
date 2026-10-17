"use server";

import { z } from "zod";
import { env } from "cloudflare:workers";
import { getD1 } from "@/db";
import type { EnquiryState } from "@/app/contact/state";

const partnershipSchema = z.object({
  fullName: z.string().trim().min(2, "Enter your name.").max(80),
  email: z.string().trim().email("Enter a valid business email.").max(160),
  organisation: z.string().trim().min(2, "Enter your organisation or write Individual.").max(120),
  role: z.string().trim().min(2, "Enter your role.").max(80),
  phone: z.string().trim().max(30),
  interest: z.enum(["investment", "sponsorship", "strategic-partnership", "technology-partnership", "other"], { message: "Select a partnership interest." }),
  message: z.string().trim().min(30, "Tell us more about your proposal (at least 30 characters).").max(3000),
  consent: z.literal("on", { message: "Consent is required to contact you." }),
  website: z.string().max(0).optional(),
});

export async function submitPartnershipEnquiry(_state: EnquiryState, formData: FormData): Promise<EnquiryState> {
  const parsed = partnershipSchema.safeParse({
    fullName: formData.get("fullName"),
    email: formData.get("email"),
    organisation: formData.get("organisation"),
    role: formData.get("role"),
    phone: formData.get("phone") ?? "",
    interest: formData.get("interest"),
    message: formData.get("message"),
    consent: formData.get("consent"),
    website: formData.get("website") ?? "",
  });
  if (!parsed.success) {
    const errors = Object.fromEntries(
      Object.entries(parsed.error.flatten().fieldErrors).map(([key, messages]) => [key, messages?.[0] ?? "Check this field."]),
    );
    return { status: "error", message: "Please check the highlighted fields.", errors };
  }

  const data = parsed.data;
  const subject = `Project support — ${data.interest.replaceAll("-", " ")}`;
  const message = [
    "INVESTOR / PARTNER ENQUIRY — NOT A STUDENT SUPPORT REQUEST",
    `Organisation: ${data.organisation}`,
    `Role: ${data.role}`,
    `Area of interest: ${data.interest.replaceAll("-", " ")}`,
    "",
    data.message,
  ].join("\n");
  const success = {
    status: "success" as const,
    message: "Thank you for your interest in partnering with Amaris. Our team will review your proposal and contact you using the details provided.",
  };

  try {
    const bindings = env as unknown as { CMS_API_URL?: string };
    const cmsBaseUrl = (bindings.CMS_API_URL || process.env.CMS_API_URL)?.replace(/\/$/, "");
    if (cmsBaseUrl) {
      try {
        const response = await fetch(`${cmsBaseUrl}/enquiries/`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            name: data.fullName,
            email: data.email.toLowerCase(),
            phone: data.phone,
            subject,
            message,
          }),
          signal: AbortSignal.timeout(6_000),
        });
        if (response.ok) return success;
        console.error("Django rejected partnership enquiry", response.status);
      } catch {
        console.error("Django partnership enquiry endpoint unavailable");
      }
    }

    const db = getD1();
    await db.prepare(`
      INSERT INTO contact_enquiries (id, full_name, email, phone, enquiry_type, message, consent_given, status)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `).bind(
      crypto.randomUUID(),
      data.fullName,
      data.email.toLowerCase(),
      data.phone || null,
      "project-partnership",
      `${subject}\n${message}`,
      1,
      "new",
    ).run();
    return success;
  } catch {
    console.error("Unable to save partnership enquiry");
    return { status: "error", message: "Your enquiry could not be submitted. Please try again or contact Amaris using the company email." };
  }
}
