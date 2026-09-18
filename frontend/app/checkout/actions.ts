"use server";

import { redirect } from "next/navigation";
import { requireVerifiedStudent } from "@/lib/auth";
import { studentApi } from "@/lib/backend";

type CheckoutStart = {
  reference: string;
};

export async function startCheckoutAction(formData: FormData) {
  const courseSlug = String(formData.get("courseSlug") ?? "").trim();
  const idempotencyKey = String(formData.get("idempotencyKey") ?? "").trim();
  if (!/^[a-z0-9-]{2,200}$/i.test(courseSlug) || !/^[A-Za-z0-9_-]{8,64}$/.test(idempotencyKey)) {
    redirect("/courses?checkout_error=invalid");
  }

  await requireVerifiedStudent(`/courses/${courseSlug}`);
  let checkout: CheckoutStart;
  try {
    checkout = await studentApi<CheckoutStart>("/student/checkout/", {
      method: "POST",
      body: JSON.stringify({
        course_slug: courseSlug,
        idempotency_key: idempotencyKey,
      }),
    });
  } catch {
    redirect(`/courses/${encodeURIComponent(courseSlug)}?checkout_error=unavailable`);
  }

  redirect(`/checkout/${encodeURIComponent(checkout.reference)}`);
}
