"""Authenticated, synthetic Django Jazzmin admin browser acceptance.

Only a disposable SQLite database running at localhost is used.
No production credentials, customer information, S3 or payment actions.
"""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"
OUT = Path(os.environ.get("AMARIS_ADMIN_BROWSER_ARTIFACTS", "/tmp/amaris-admin-browser"))
OUT.mkdir(parents=True, exist_ok=True)


def login(page, username, password):
    response = page.goto(BASE + "/admin/login/?next=/admin/", wait_until="domcontentloaded")
    assert response and response.status == 200, "Admin login not accessible"
    user_field = page.locator('input[name="username"]').first
    password_field = page.locator('input[name="password"]').first
    if not user_field.count() or not password_field.count():
        page.screenshot(path=str(OUT / "login-diagnostic.png"), full_page=True)
        print("BLOCK synthetic login page:",
              json.dumps({
                  "path": page.url.split("?", 1)[0],
                  "title": page.title(),
                  "input_types": page.locator("input").evaluate_all(
                      "(nodes) => nodes.map(x => [x.type, x.name, x.id])"),
                  "h1": page.locator("h1").all_text_contents()[:3],
              }), flush=True)
        raise AssertionError("Django Jazzmin login fields missing")
    user_field.fill(username)
    password_field.fill(password)
    page.locator('input[type="submit"]').first.click()
    page.wait_for_url("**/admin/**", timeout=15000)
    assert "/admin/login/" not in page.url, "Synthetic account could not authenticate"


def check_index(page, width, reduced_motion):
    page.set_viewport_size({"width": width, "height": 850})
    page.emulate_media(reduced_motion="reduce" if reduced_motion else "no-preference")
    response = page.goto(BASE + "/admin/", wait_until="networkidle")
    assert response and response.status == 200
    assert page.locator(".amaris-admin-welcome").count() == 1
    assert page.locator(".amaris-admin-shortcut").count() >= 3
    monitoring = page.get_by_role("link", name="Open monitoring")
    assert monitoring.count() == 1, "Superuser monitoring shortcut missing"

    # Confirm the deployed Jazzmin hook loads the exact local static resources.
    for name, expected_type in (
        ("amaris-admin.css", "text/css"),
        ("amaris-admin.js", "javascript"),
    ):
        url = BASE + "/static/content/admin/" + name
        response = page.request.get(url)
        assert response.status == 200, f"{name}: HTTP {response.status}"
        assert expected_type in response.headers.get("content-type", "").lower()
    assert page.evaluate("""() => [...document.styleSheets].some(sheet =>
        (sheet.href || '').includes('amaris-admin.css'))""")

    shortcut = page.locator(".amaris-admin-shortcut").first
    shortcut.focus()
    outline = shortcut.evaluate("(el) => getComputedStyle(el).outlineWidth")
    assert float(outline.replace("px", "")) >= 2, "Keyboard focus indicator not visible"
    if reduced_motion:
        duration = shortcut.evaluate("(el) => getComputedStyle(el).transitionDuration")
        assert all(float(part.strip().rstrip("s")) == 0 for part in duration.split(",")), (
            "Reduced-motion media preference was not honoured"
        )

    size = page.evaluate("""() => ({width: window.innerWidth,
        pageWidth: document.documentElement.scrollWidth})""")
    assert size["pageWidth"] <= size["width"] + 3, f"Dashboard horizontal overflow {size}"
    page.screenshot(path=str(OUT / f"superuser-dashboard-{width}.png"), full_page=True)
    print(f"PASS admin dashboard {width}px, local assets, role-based shortcuts, focus and reduced motion")


def test_form_save(page):
    url = BASE + "/admin/content/coursecategory/add/"
    assert page.goto(url, wait_until="networkidle").status == 200
    form = page.locator("form[id$='_form']")
    assert form.count() == 1
    assert form.locator(".submit-row").count() == 1
    page.locator("#id_name").fill("Synthetic Admin Browser Course Category")
    page.locator("#id_slug").fill("synthetic-admin-browser-course-category")
    # Cancel navigation in this synthetic browser check only to inspect
    # the transient status. Normal Django form controls remain untouched.
    page.evaluate("""() => document.querySelector("form[id$='_form']")
        .addEventListener('submit', (event) => event.preventDefault())""")
    page.locator('input[name="_save"]').first.click()
    status = form.get_by_role("status")
    assert status.count() == 1 and "Submitting changes" in status.inner_text()
    assert not page.locator('input[name="_save"]').first.is_disabled()
    print("PASS native form validation, non-blocking save indicator, enabled retry controls")
    # Fresh navigation restores ordinary Django form handling and persists to
    # the local-only SQLite fixture.
    page.goto(url, wait_until="domcontentloaded")
    page.locator("#id_name").fill("Synthetic Admin Browser Course Category")
    page.locator("#id_slug").fill("synthetic-admin-browser-course-category")
    page.locator('input[name="_save"]').first.click()
    page.wait_for_url("**/admin/content/coursecategory/", timeout=15000)
    assert page.get_by_text("Synthetic Admin Browser Course Category").count() >= 1
    print("PASS actual Django Admin create-and-redirect with synthetic SQLite data")


def test_list(page, width):
    page.set_viewport_size({"width": width, "height": 850})
    response = page.goto(BASE + "/admin/content/coursecategory/", wait_until="networkidle")
    assert response and response.status == 200
    assert page.locator("#result_list tbody tr").count() <= 30
    assert page.locator(".paginator").count() >= 1
    page.screenshot(path=str(OUT / f"category-list-{width}.png"), full_page=True)
    print(f"PASS admin paginated table at {width}px, bounded to 30 rows")


def test_staff(browser, username, password):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    login(page, username, password)
    response = page.goto(BASE + "/admin/", wait_until="networkidle")
    assert response and response.status == 200
    assert page.get_by_role("link", name="Open monitoring").count() == 0
    assert page.locator('a[href="/admin/content/announcement/"]').count() == 0
    assert page.locator('a[href="/admin/content/tutorpaymentprofile/"]').count() == 0
    forbidden = page.goto(BASE + "/admin/content/announcement/")
    assert forbidden and forbidden.status in (302, 403, 404), (
        "Ordinary staff could access superuser-only marketing administration"
    )
    print("PASS ordinary staff cannot see superuser monitoring/marketing and cannot access marketing changelist")
    context.close()


def main():
    admin_user = os.environ["AMARIS_ADMIN_BROWSER_SUPERUSER"]
    staff_user = os.environ["AMARIS_ADMIN_BROWSER_STAFF"]
    password = os.environ["AMARIS_ADMIN_BROWSER_PASSWORD"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        login(page, admin_user, password)
        for width in (320, 390, 768, 1440):
            check_index(page, width, reduced_motion=width in (320, 390))
        test_form_save(page)
        for width in (320, 1440):
            test_list(page, width)
        context.close()
        test_staff(browser, staff_user, password)
        browser.close()
    report = {"result": "PASS", "sizes": [320, 390, 768, 1440],
              "auth": "synthetic-local-only", "production_writes": False}
    (OUT / "acceptance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS all authenticated Django Jazzmin admin browser acceptance checks")


if __name__ == "__main__":
    main()
