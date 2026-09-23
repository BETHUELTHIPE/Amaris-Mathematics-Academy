import re


def website_fallback(question: str) -> str:
    """Give limited public website guidance when the AI provider is unavailable."""
    words = question.lower()
    prefix = "Live AI is unavailable right now. From the published website: "

    if re.search(r"forgot|reset|password", words):
        return prefix + (
            "Use /forgot-password to request a secure password reset link. "
            "Never share your password or reset link in this chat."
        )
    if re.search(r"register|sign up|create (a |my )?(profile|account)|join|enrol", words):
        return prefix + (
            "Create your profile at /register, then verify your email using the six-digit code "
            "or the link in your verification email. You can log in at /login."
        )
    if re.search(r"log in|login|sign in|verify|verification", words):
        return prefix + (
            "Verify your email using the six-digit code or confirmation link sent after registration "
            "at /verify-email, then log in at /login."
        )
    if re.search(r"pric|cost|fee|pay|checkout|invoice|subscription", words):
        return prefix + (
            "See /pricing and /courses for current published prices. Verified students can continue "
            "to secure checkout from a course page. I cannot see individual payment or invoice status."
        )
    if re.search(r"course|study|programme|program|pathway|subject|curriculum|math", words):
        return prefix + "Browse /courses for currently published courses, subjects, and prices."
    if re.search(r"contact|email|phone|support|address|hours", words):
        return prefix + "The current support details and enquiry form are at /contact."
    return (
        "Live AI is unavailable right now, so I cannot verify an answer to that question. "
        "Please check /courses, /pricing or /contact for published information."
    )
