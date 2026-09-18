"use server";

import { z } from "zod";
import { env } from "cloudflare:workers";
import { getD1 } from "@/db";
import type { EnquiryState } from "@/app/contact/state";

const enquirySchema = z.object({
  fullName: z.string().trim().min(2, "Enter your full name.").max(80, "Keep your name under 80 characters."),
  email: z.string().trim().email("Enter a valid email address.").max(160, "Keep your email under 160 characters."),
  phone: z.string().trim().max(30, "Keep your phone number under 30 characters."),
  enquiryType: z.enum(["course-guidance", "registration", "payments", "student-account", "technical-support", "other"], { message: "Choose an enquiry type." }),
  message: z.string().trim().min(20, "Please provide at least 20 characters so we can help you.").max(2000, "Keep your message under 2,000 characters."),
  consent: z.literal("on", { message: "Please agree so that we may respond to your enquiry." }),
  website: z.string().max(0).optional(),
});

export async function submitEnquiry(_previousState: EnquiryState, formData: FormData): Promise<EnquiryState> {
  const parsed = enquirySchema.safeParse({
    fullName: formData.get("fullName"),
    email: formData.get("email"),
    phone: formData.get("phone") ?? "",
    enquiryType: formData.get("enquiryType"),
    message: formData.get("message"),
    consent: formData.get("consent"),
    website: formData.get("website") ?? "",
  });

  if (!parsed.success) {
    const errors = Object.fromEntries(Object.entries(parsed.error.flatten().fieldErrors).map(([field, messages]) => [field, messages?.[0] ?? "Check this field."]));
    return { status: "error", message: "Please check the highlighted fields.", errors };
  }

  try {
    const workerBindings = env as unknown as { CMS_API_URL?: string };
    const cmsBaseUrl = (workerBindings.CMS_API_URL || process.env.CMS_API_URL)?.replace(/\/$/, "");
    if (cmsBaseUrl) {
      try {
        const cmsResponse = await fetch(`${cmsBaseUrl}/enquiries/`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            name: parsed.data.fullName,
            email: parsed.data.email.toLowerCase(),
            phone: parsed.data.phone,
            subject: parsed.data.enquiryType.replaceAll("-", " "),
            message: parsed.data.message,
          }),
          signal: AbortSignal.timeout(6_000),
        });
        if (cmsResponse.ok) {
          return { status: "success", message: "Thank you. Your enquiry has been received, and the Amaris team will respond as soon as possible." };
        }
        console.error("Django CMS rejected contact enquiry", cmsResponse.status);
      } catch (cmsError) {
        console.error("Django CMS contact endpoint unavailable", cmsError);
      }
    }

    const db = getD1();
    await db.prepare(`
      INSERT INTO contact_enquiries (id, full_name, email, phone, enquiry_type, message, consent_given, status)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `).bind(
      crypto.randomUUID(),
      parsed.data.fullName,
      parsed.data.email.toLowerCase(),
      parsed.data.phone || null,
      parsed.data.enquiryType,
      parsed.data.message,
      1,
      "new",
    ).run();

    return { status: "success", message: "Thank you. Your enquiry has been received, and the Amaris team will respond as soon as possible." };
  } catch (error) {
    console.error("Unable to save contact enquiry", error);
    return { status: "error", message: "We could not send your enquiry right now. Please try again or contact us by phone or email." };
  }
}
