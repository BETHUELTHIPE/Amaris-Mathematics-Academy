export type RecoveryKind =
  | "request"
  | "permission"
  | "missing"
  | "rate-limit"
  | "server"
  | "maintenance"
  | "payment"
  | "session"
  | "connection";

export type RecoveryAction = {
  label: string;
  href?: string;
  retry?: boolean;
};

export type RecoveryDefinition = {
  code?: string;
  eyebrow: string;
  title: string;
  message: string;
  reassurance?: string;
  kind: RecoveryKind;
  primaryAction: RecoveryAction;
  secondaryAction?: RecoveryAction;
  showSupport?: boolean;
};

export const httpRecoveryDefinitions = {
  "400": {
    code: "400",
    eyebrow: "Request not understood",
    title: "Let’s try that again.",
    message:
      "We could not safely process the request. Check the information you entered, then return and try once more.",
    reassurance:
      "If you were completing a form, the safe fields may still be available when you go back.",
    kind: "request",
    primaryAction: { label: "Go back", href: "back" },
    secondaryAction: { label: "Return home", href: "/" },
    showSupport: true,
  },
  "403": {
    code: "403",
    eyebrow: "Access restricted",
    title: "You do not have access to this page.",
    message:
      "This area may require a verified student account, an active enrolment, or staff permission.",
    reassurance:
      "Signing in with the correct account is the safest next step. Course access is never granted from a browser message alone.",
    kind: "permission",
    primaryAction: { label: "Log in securely", href: "/login" },
    secondaryAction: { label: "View my dashboard", href: "/dashboard" },
    showSupport: true,
  },
  "404": {
    code: "404",
    eyebrow: "Page not found",
    title: "That page is not on the syllabus.",
    message:
      "The address may be outdated, mistyped, or the page may have moved.",
    reassurance:
      "Your account, payments, and course progress have not been changed.",
    kind: "missing",
    primaryAction: { label: "Browse mathematics courses", href: "/courses" },
    secondaryAction: { label: "Return home", href: "/" },
    showSupport: true,
  },
  "429": {
    code: "429",
    eyebrow: "Please slow down",
    title: "Too many attempts were made.",
    message:
      "We have temporarily paused new attempts to help protect your account and the academy.",
    reassurance:
      "Wait a few minutes before trying again. Repeated clicks will not make the wait shorter.",
    kind: "rate-limit",
    primaryAction: { label: "Try again", retry: true },
    secondaryAction: { label: "Return home", href: "/" },
    showSupport: true,
  },
  "500": {
    code: "500",
    eyebrow: "Something went wrong",
    title: "We could not complete that action.",
    message:
      "The academy website encountered an unexpected problem. No technical details are shown here for your security.",
    reassurance:
      "Please try once more. If this happened during payment, check your order status before paying again.",
    kind: "server",
    primaryAction: { label: "Try again", retry: true },
    secondaryAction: { label: "Go to dashboard", href: "/dashboard" },
    showSupport: true,
  },
  "502": {
    code: "502",
    eyebrow: "Service connection interrupted",
    title: "One of our services did not respond.",
    message:
      "The website is available, but a supporting service could not be reached just now.",
    reassurance:
      "Please wait a moment and retry. Do not repeat a payment until you have checked your order status.",
    kind: "server",
    primaryAction: { label: "Try again", retry: true },
    secondaryAction: { label: "Check my orders", href: "/dashboard" },
    showSupport: true,
  },
  "503": {
    code: "503",
    eyebrow: "Temporarily unavailable",
    title: "We’ll be back shortly.",
    message:
      "The academy is undergoing maintenance or is temporarily busy.",
    reassurance:
      "Your account and course records remain protected. Please try again in a few minutes.",
    kind: "maintenance",
    primaryAction: { label: "Check again", retry: true },
    secondaryAction: { label: "Return home", href: "/" },
    showSupport: true,
  },
} satisfies Record<string, RecoveryDefinition>;

export const experienceRecoveryDefinitions = {
  "payment-processing": {
    eyebrow: "Payment processing",
    title: "Your payment is being processed.",
    message:
      "Your checkout has been submitted and the academy is waiting for a verified payment result.",
    reassurance:
      "Please do not pay again or close this page repeatedly. Check your dashboard before starting another checkout.",
    kind: "payment",
    primaryAction: { label: "Check order status", href: "/dashboard" },
    secondaryAction: { label: "Return to courses", href: "/courses" },
    showSupport: true,
  },
  "payment-paid": {
    eyebrow: "Payment confirmed",
    title: "Payment confirmed.",
    message:
      "Your verified payment has been accepted and your course access can now be opened from your dashboard.",
    reassurance:
      "Keep your order reference for your records. Amaris will never ask you to repeat a completed payment by email or phone.",
    kind: "payment",
    primaryAction: { label: "Open my dashboard", href: "/dashboard" },
    secondaryAction: { label: "Browse courses", href: "/courses" },
    showSupport: true,
  },
  "payment-expired": {
    eyebrow: "Checkout expired",
    title: "This checkout session has expired.",
    message:
      "The payment window ended before a verified payment was completed.",
    reassurance:
      "No course access is activated from an expired checkout. Check your dashboard before starting a fresh payment.",
    kind: "payment",
    primaryAction: { label: "Check order status", href: "/dashboard" },
    secondaryAction: { label: "Return to courses", href: "/courses" },
    showSupport: true,
  },
  "payment-refunded": {
    eyebrow: "Refund recorded",
    title: "Your refund has been recorded.",
    message:
      "This order is marked as refunded. Any related course-access changes are shown on your dashboard.",
    reassurance:
      "Refund settlement timing can depend on the payment provider and your bank. Keep your order reference if you contact support.",
    kind: "payment",
    primaryAction: { label: "Open my dashboard", href: "/dashboard" },
    secondaryAction: { label: "Contact support", href: "/contact" },
    showSupport: true,
  },
  "payment-pending": {
    eyebrow: "Payment processing",
    title: "Your payment is still being confirmed.",
    message:
      "PayFast has not yet sent a verified payment confirmation to the academy.",
    reassurance:
      "Please do not pay again. Course access will appear only after the verified PayFast notification is received.",
    kind: "payment",
    primaryAction: { label: "Check order status", href: "/dashboard" },
    secondaryAction: { label: "Return to courses", href: "/courses" },
    showSupport: true,
  },
  "payment-cancelled": {
    eyebrow: "Payment cancelled",
    title: "No payment was completed.",
    message:
      "You left the PayFast checkout before payment was confirmed.",
    reassurance:
      "No course access has been activated. You can safely return to your course and start checkout again when ready.",
    kind: "payment",
    primaryAction: { label: "Return to courses", href: "/courses" },
    secondaryAction: { label: "View my dashboard", href: "/dashboard" },
    showSupport: true,
  },
  "payment-failed": {
    eyebrow: "Payment not completed",
    title: "PayFast could not complete the payment.",
    message:
      "Your course has not been activated. The payment may have been declined or interrupted.",
    reassurance:
      "Check your order status before trying again. Amaris never asks for card details by email or phone.",
    kind: "payment",
    primaryAction: { label: "Check order status", href: "/dashboard" },
    secondaryAction: { label: "Return to courses", href: "/courses" },
    showSupport: true,
  },
  "session-expired": {
    eyebrow: "Session ended",
    title: "Please log in again.",
    message:
      "Your secure session ended because it expired or your account was signed out.",
    reassurance:
      "This protects your student information. Safe unsaved form fields may still be available in this browser tab.",
    kind: "session",
    primaryAction: { label: "Log in securely", href: "/login" },
    secondaryAction: { label: "Return home", href: "/" },
    showSupport: true,
  },
  "connection-lost": {
    eyebrow: "Connection lost",
    title: "You appear to be offline.",
    message:
      "The website cannot reach the internet right now. Keep this tab open while you reconnect.",
    reassurance:
      "Safe form fields are kept in this tab where possible. Passwords, verification codes, payment details, and uploads are never saved as drafts.",
    kind: "connection",
    primaryAction: { label: "Check connection", retry: true },
    secondaryAction: { label: "Return home", href: "/" },
    showSupport: true,
  },
} satisfies Record<string, RecoveryDefinition>;

export function createCorrelationReference(): string {
  const timestamp = Date.now().toString(36).toUpperCase();
  const random = crypto.randomUUID().replaceAll("-", "").slice(0, 8).toUpperCase();
  return `AMR-${timestamp}-${random}`;
}
