"""Exercise real booking components in an isolated build. No external POSTs."""
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

BASE = os.getenv("E2E_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
OUT = Path("artifacts/school-curriculum")
OUT.mkdir(parents=True, exist_ok=True)
GRADES = [f"Grade {grade}" for grade in range(7, 13)]


def verify(scope, include_topic):
    programme = scope.get_by_role("combobox", name="Programme", exact=True)
    subject = scope.get_by_role("combobox", name="Subject", exact=True)
    level = scope.get_by_role("combobox", name="Grade / level", exact=True)
    for curriculum in ("caps", "ieb"):
        programme.select_option(curriculum)
        subject.select_option("mathematics")
        choices = level.locator("option").evaluate_all("es => es.map(e => e.value)")
        assert all(grade in choices for grade in GRADES), choices
        for grade in GRADES:
            level.select_option(grade)
            expect(scope.get_by_text(f"View {curriculum.upper()} {grade} Mathematics syllabus guide", exact=True)).to_be_visible()
            if include_topic:
                topic = scope.get_by_role("combobox", name="Topic / chapter", exact=True)
                assert topic.locator("option").count() >= 12
                chapter = topic.locator("option").nth(1).get_attribute("value")
                topic.select_option(chapter)
                assert topic.input_value() == chapter
        level.select_option("Grade 7")
        if include_topic:
            expect(scope.get_by_role("combobox", name="Topic / chapter", exact=True)).to_have_value("")
        subject.select_option("mathematical_literacy")
        expect(level).to_have_value("")
        choices = level.locator("option").evaluate_all("es => es.map(e => e.value)")
        assert all(grade not in choices for grade in GRADES[:3]), choices
        assert all(grade in choices for grade in GRADES[3:]), choices
    programme.select_option("university")
    subject.select_option("mathematics")
    level.select_option("__custom__")
    scope.get_by_label("Academic level or module", exact=True).fill("UNISA MAT2611")
    if include_topic:
        scope.get_by_role("combobox", name="Topic / chapter", exact=True).select_option("__custom__")
        custom = scope.get_by_label("Your topic, chapter or question", exact=True)
        assert custom.evaluate("e => e.required && e.validity.valueMissing")
        custom.fill("Assignment 2, question 4")
        values = scope.locator("form").evaluate("e => Object.fromEntries(new FormData(e))")
        assert values["customLevel"] == "UNISA MAT2611" and values["customTopic"] == "Assignment 2, question 4"
    programme.select_option("caps")
    expect(level).to_have_value("")
    if include_topic:
        expect(scope.get_by_role("combobox", name="Topic / chapter", exact=True)).to_have_value("")


with sync_playwright() as p:
    for engine in ("chromium", "firefox", "webkit"):
        for width in (320, 834, 1440):
            browser = getattr(p, engine).launch()
            context = browser.new_context(viewport={"width": width, "height": 1000})
            posts = []
            def block(route):
                if route.request.method == "POST":
                    posts.append(route.request.url)
                    route.abort()
                else:
                    route.continue_()
            context.route("**/*", block)
            page = context.new_page()
            page.goto(BASE + "/curriculum-test-fixture", wait_until="networkidle")
            # Existing tutor settings remain intact when editing.
            edit = page.locator("#edit-slot")
            expect(edit.get_by_role("combobox", name="Programme", exact=True)).to_have_value("ieb")
            expect(edit.get_by_role("combobox", name="Grade / level", exact=True)).to_have_value("Grade 11")
            for name in ("live", "video", "create-slot", "edit-slot"):
                verify(page.locator("#" + name), name in ("live", "video"))
            page.add_script_tag(path="node_modules/axe-core/axe.min.js")
            violations = page.evaluate("async () => (await axe.run(document.querySelector('main'), {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}})).violations")
            assert not violations, json.dumps(violations)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
            assert not posts, posts
            page.screenshot(path=str(OUT / f"{engine}-{width}.png"), full_page=True)
            print(f"PASS {engine}/{width}: live/video/tutor create/edit, CAPS+IEB all six grades, chapters, reset, custom entries, axe and overflow", flush=True)
            context.close()
            browser.close()

    browser = p.chromium.launch()
    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    page.goto(BASE + "/book-online-live-class?programme=caps&subject=mathematics", wait_until="networkidle")
    destination = urlparse(page.url)
    assert destination.path == "/login", f"Anonymous user reached private booking page: {destination.path}"
    saved = parse_qs(destination.query).get("next", [""])[0]
    assert saved == "/book-online-live-class?programme=caps&subject=mathematics", saved
    expect(page.get_by_role("heading", name="Welcome back.")).to_be_visible()
    print("PASS JavaScript-disabled anonymous booking redirected to sign-in with saved curriculum choices", flush=True)
    browser.close()
