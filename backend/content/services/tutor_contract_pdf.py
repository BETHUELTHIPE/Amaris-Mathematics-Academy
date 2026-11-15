"""Professional A4 tutor employment agreements on the academy letterhead."""

from io import BytesIO

from reportlab.lib import colors
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Spacer

from content.models import SiteSettings
from content.services.invoice_document import (
    BLUE,
    CONTENT_WIDTH,
    GOLD,
    HEIGHT,
    LINE,
    MARGIN,
    NAVY,
    WIDTH,
    _logo,
    _paragraph,
    _register_fonts,
)


def contract_summary_lines(item):
    p = item.payload
    return [
        ("Tutor", p["tutor_name"]),
        ("Tutor email", p["tutor_email"]),
        ("Preferred commencement date", p["preferred_start_date"]),
        ("Submitted", p["submitted_at"]),
        ("Typed signature", p["signature_name"]),
        ("Status", item.get_status_display()),
    ]


def _clauses(item, executed):
    p = item.payload
    days = ", ".join(p["ordinary_work_days"])
    service_terms = "; ".join(
        f"{term['service_label']}: Admin (Academy) {term['academy_percent']}% / Tutor {term['tutor_percent']}% "
        + (
            f"/ Platform operating costs {term['platform_percent']}% "
            if "platform_percent" in term
            else ""
        )
        + f"(reference {term['contract_reference']})"
        for term in item.service_terms
    )
    platform_note = (
        "The platform allocation is earmarked for operating costs and is not deducted again from the Tutor's share. "
        if any("platform_percent" in term for term in item.service_terms)
        else ""
    )
    signature = (
        f"For the employer: {item.employer_signature_name}; effective {item.effective_date}."
        if executed
        else "Employer countersignature: pending Super User review. This submission does not activate teaching access."
    )
    return [
        (
            "1. Parties and appointment",
            f"Amaris Mathematics Academy (the Employer) offers {p['tutor_name']} ({p['tutor_email']}) employment as a "
            "part-time, variable-hours online tutor. The normal place of work is remote, using the Academy "
            "dashboard and "
            "approved Zoom links. The preferred commencement date is " + p["preferred_start_date"] + ".",
        ),
        (
            "2. Duties and booking workflow",
            "The Tutor publishes accurate availability; accepts only Academy-assigned bookings; prepares and "
            "delivers the advertised CAPS, IEB, TVET or university lesson; uses the protected student and Zoom "
            "details only for that booking; records attendance and completion; provides reasonable learning "
            "feedback; and promptly reports any absence, safeguarding concern, technical failure or required "
            "handover. Unverified or unpaid bookings do not authorise disclosure of student contact details. "
            "A dashboard cancellation alone does not cancel a paid lesson.",
        ),
        (
            "3. Hours and availability",
            f"The Tutor's indicated ordinary days are {days}, with a maximum of "
            f"{p['maximum_weekly_hours']} accepted hours per week. Availability is not a guarantee of bookings "
            "or hours. The Tutor is not required to work outside an accepted schedule. Ordinary hours will not "
            "exceed the Basic Conditions of Employment Act limits. Overtime, "
            "Sunday and public-holiday work requires prior written approval and will be treated as required by law.",
        ),
        (
            "4. Remuneration",
            "The agreed revenue split for each service is captured below, calculated on the gross service sale "
            f"recorded by the booking system: {service_terms}. {platform_note}These shares are "
            "variable or incentive remuneration and do not replace the statutory wage floor. For every ordinary "
            "hour actually worked, the Employer will top up remuneration when necessary to at least "
            f"R{item.statutory_hourly_floor:.2f} per hour (the national minimum applying from 1 March 2026), or "
            "any later higher legal minimum. Remuneration is processed monthly and paid no later than seven days "
            "after the end of the pay period. The system's seven-day payment and service-completion hold applies "
            "to provisional service-share earnings only and may not unlawfully delay base "
            "wages. The Employer will provide a payslip and make lawful PAYE, UIF and other authorised deductions.",
        ),
        (
            "5. Leave and absence",
            "Annual, sick, family-responsibility, maternity, parental and other leave accrue and are administered "
            "at least at the statutory minimum. The Tutor must use the dashboard leave form as early as reasonably "
            "possible and identify affected lessons and a handover plan. A medical certificate may be requested "
            "when permitted by law.",
        ),
        (
            "6. Student protection, privacy and confidentiality",
            "Student identities, contact information, recordings, learning records, payment data, credentials and "
            "internal Academy information are confidential. The Tutor will comply with POPIA, use only authorised "
            "systems and assigned booking data, avoid local copies where reasonably possible, never share "
            "credentials, and immediately report a suspected data or safeguarding incident. Private student "
            "information must not be used for personal marketing.",
        ),
        (
            "7. Professional conduct and safeguarding",
            "The Tutor will maintain appropriate adult-learner boundaries, communicate through approved channels, "
            "teach without discrimination or harassment, avoid private financial arrangements with students, and "
            "comply with Academy safeguarding, assessment, quality and complaints procedures. Lessons may be "
            "quality-reviewed on lawful "
            "notice. Serious misconduct may lead to precautionary suspension and a fair process.",
        ),
        (
            "8. Materials and intellectual property",
            "Each party retains pre-existing intellectual property. The Tutor grants the Employer a non-exclusive, "
            "worldwide, royalty-free licence to store and use lesson plans, worksheets and feedback submitted for "
            "booked services for teaching, moderation, compliance and learner support. A separate written commission "
            "is required before ownership "
            "of substantial original course or video material transfers. Student work remains confidential.",
        ),
        (
            "9. Equipment and remote work",
            "Unless separately agreed, the Tutor supplies a suitable computer, camera, microphone and reliable "
            "connectivity, keeps software updated and works from a private, safe environment. Approved business "
            "expenses require prior written authorisation. The Tutor must notify the Employer when equipment or "
            "connectivity prevents safe delivery.",
        ),
        (
            "10. Discipline, incapacity and termination",
            "Performance, incapacity, misconduct, operational requirements and dismissal will be handled under the "
            "Labour Relations Act and applicable Code of Practice. Either party may terminate on the written notice "
            "required by the Basic Conditions of Employment Act or a longer mutually agreed lawful period. The "
            "dashboard resignation form records notice but does not waive a fair process, accrued remuneration, "
            "handover or confidentiality obligations.",
        ),
        (
            "11. General terms",
            "This agreement, the captured service terms and lawful Academy policies form the employment record. "
            "A policy may not reduce a statutory right. Changes to pay, duties or status require a written record "
            "accepted by both parties. South African law applies. If a clause is invalid, the remaining clauses "
            "continue. Disputes should first be raised internally without limiting access to the CCMA, Department "
            "of Employment and Labour or a competent court.",
        ),
        (
            "12. Electronic acceptance",
            f"Tutor signature: {p['signature_name']} on {p['submitted_at']}. The Tutor confirmed the employment "
            "terms, POPIA "
            f"notice, safeguarding duties and use of an electronic signature. {signature}",
        ),
        (
            "Important review note",
            "Terms version "
            + item.terms_version
            + ". The statutory rate and legal wording must be reviewed before 1 March "
            "2027 and whenever employment law or the booking/payment workflow changes.",
        ),
    ]


def render_tutor_contract(item, *, executed=False):
    _register_fonts()
    site = SiteSettings.objects.first() or SiteSettings()
    logo = _logo(site)
    output = BytesIO()

    def letterhead(page, doc):
        page.saveState()
        page.setTitle(f"Tutor contract of employment - {item.pk}")
        page.setAuthor(site.site_name)
        for x, fraction, color in ((0, 0.58, NAVY), (WIDTH * 0.58, 0.24, BLUE), (WIDTH * 0.82, 0.18, GOLD)):
            page.setFillColor(color)
            page.rect(x, HEIGHT - 5, WIDTH * fraction, 5, fill=1, stroke=0)
        page.drawImage(logo, MARGIN, HEIGHT - 83, width=52, height=52, preserveAspectRatio=True, mask="auto")
        title = _paragraph(site.site_name, size=15, color=NAVY, bold=True)
        title.wrap(CONTENT_WIDTH - 70, 30)
        title.drawOn(page, MARGIN + 66, HEIGHT - 47)
        contact = _paragraph(f"{site.phone} · {site.email}<br/>{site.address}", size=7)
        contact.wrap(CONTENT_WIDTH - 70, 35)
        contact.drawOn(page, MARGIN + 66, HEIGHT - 78)
        page.setStrokeColor(LINE)
        page.line(MARGIN, HEIGHT - 103, WIDTH - MARGIN, HEIGHT - 103)
        page.setStrokeColor(GOLD)
        page.line(MARGIN, 55, WIDTH - MARGIN, 55)
        footer = _paragraph(
            f"{site.site_name} · Confidential employment record · Reference {item.pk} · Page {doc.page}", size=7
        )
        footer.wrap(CONTENT_WIDTH, 25)
        footer.drawOn(page, MARGIN, 28)
        page.restoreState()

    document = BaseDocTemplate(output, pagesize=(WIDTH, HEIGHT))
    document.addPageTemplates(
        PageTemplate(
            id="contract",
            frames=[Frame(MARGIN, 68, CONTENT_WIDTH, HEIGHT - 188, leftPadding=0, rightPadding=0)],
            onPage=letterhead,
        )
    )
    status = "EXECUTED COPY" if executed else "TUTOR-SIGNED COPY · EMPLOYER ACCEPTANCE PENDING"
    story = [
        _paragraph("Tutor contract of employment", size=18, color=NAVY, bold=True),
        _paragraph(status, size=8, color=BLUE, bold=True),
        Spacer(1, 12),
    ]
    for heading, body in _clauses(item, executed):
        label = _paragraph(heading.upper(), size=8, color=BLUE, bold=True)
        label.keepWithNext = True
        story.extend([label, _paragraph(body, size=8.5, color=colors.HexColor("#263852")), Spacer(1, 9)])
    document.build(story)
    return output.getvalue()
