// Public website guidance for temporary AI outages. Keep dynamic prices and
// private account information out of these answers.
export function websiteFallback(question: string): string {
  const words = question.toLowerCase();
  const prefix = "Live AI is unavailable right now. From the published website: ";

  if (/forgot|reset|password/.test(words)) {
    return prefix + "Use /forgot-password to request a secure password reset link. Never share your password or reset link in this chat.";
  }
  if (/register|sign up|create (a |my )?(profile|account)|join|enrol/.test(words)) {
    return prefix + "Create your profile at /register, then verify your email using the six-digit code or the link in your verification email. You can log in at /login.";
  }
  if (/log in|login|sign in|verify|verification/.test(words)) {
    return prefix + "Verify your email using the six-digit code or confirmation link sent after registration at /verify-email, then log in at /login.";
  }
  if (/pric|cost|fee|pay|checkout|invoice|subscription/.test(words)) {
    return prefix + "See /pricing and /courses for current published prices. Verified students can continue to secure checkout from a course page. I cannot see individual payment or invoice status.";
  }
  if (/course|study|programme|program|pathway|subject|curriculum|math/.test(words)) {
    return prefix + "Amaris has CAPS, IEB, TVET and university mathematics pathways. Browse the current catalogue at /courses for courses and prices.";
  }
  if (/contact|email|phone|support|address|hours/.test(words)) {
    return prefix + "The current support details and enquiry form are at /contact.";
  }
  return "Live AI is unavailable right now, so I cannot verify an answer to that question. Please check /courses, /pricing or /contact for published information.";
}
