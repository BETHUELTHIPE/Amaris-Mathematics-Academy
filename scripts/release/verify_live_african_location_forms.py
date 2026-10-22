"""Read-only production browser acceptance for Amaris African location fields.

No registration, enquiry, application, payment, email or file upload is submitted.
All POST/PATCH/PUT/DELETE requests are intercepted and aborted. This is a
public-only smoke test and prints no entered personal information.
"""
import os
import time

from playwright.sync_api import expect, sync_playwright

BASE = "https://amaris-mathematics-academy-live-students.onrender.com"
PUBLIC_ROUTES = ("/register", "/tutor/register", "/contact")


def read_page(page, route):
    last = None
    for n in range(5):
        try:
            response = page.goto(BASE + route, wait_until="domcontentloaded", timeout=55000)
            if response and response.status == 200:
                expect(page.locator("#country")).to_be_visible(timeout=20000)
                return
            last = f"HTTP {response.status if response else 'no response'}"
        except Exception as exc:
            last = type(exc).__name__
        if n < 4:
            time.sleep(3)
    raise AssertionError(f"Production route {route} unavailable: {last}")


def check_fields(page, path):
    read_page(page, path)
    country = page.locator("#country")
    province = page.locator("#province")
    city = page.locator("#city")
    assert country.locator("option").count() == 59
    country.select_option("ZA")
    expect(province).to_be_enabled()
    province.select_option("Gauteng")
    city.select_option("Pretoria")
    assert city.input_value() == "Pretoria"
    province.select_option("Western Cape")
    assert city.input_value() == "", "City wasn't cleared by province update"
    country.select_option("KE")
    assert province.input_value() == "" and city.input_value() == ""
    expect(city).to_be_disabled()
    expect(province).to_be_enabled()
    province.select_option("Nairobi County")
    city.select_option("Nairobi")
    province.select_option("__other__")
    page.locator("#provinceOther").fill("CI synthetic region")
    city.select_option("__other__")
    assert not page.locator("#cityOther").evaluate("input => input.checkValidity()")
    page.locator("#cityOther").fill("CI synthetic town")
    assert page.locator("#cityOther").evaluate("input => input.checkValidity()")
    entries = country.evaluate("input => Object.fromEntries(new FormData(input.form))")
    assert entries["country"] == "KE"
    assert entries["provinceOther"] == "CI synthetic region"
    assert entries["cityOther"] == "CI synthetic town"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
    print(f"PASS {path}: real African dropdowns, dependent resets, Other required and separate values, no overflow", flush=True)


def main():
    with sync_playwright() as pw:
        for width in (320, 390, 1440):
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(viewport={"width": width, "height": 850}, locale="en-ZA")
            forbidden = []
            def no_mutations(route):
                if route.request.method not in ("GET", "HEAD", "OPTIONS"):
                    forbidden.append(route.request.method)
                    route.abort()
                else:
                    route.continue_()
            context.route("**/*", no_mutations)
            page = context.new_page()
            page.set_default_timeout(30000)
            for route in PUBLIC_ROUTES:
                check_fields(page, route)
            assert not forbidden, f"Unexpected request methods: {forbidden}"
            context.close()
            browser.close()
            print(f"PASS chromium viewport width {width}: all public forms; zero POST requests", flush=True)

        # The JavaScript-disabled GET-only picker is a critical fallback.
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(java_script_enabled=False)
        context.route("**/*", lambda route: route.abort() if route.request.method not in ("GET", "HEAD", "OPTIONS") else route.continue_())
        page = context.new_page()
        page.goto(BASE + "/locations?returnTo=/contact", wait_until="domcontentloaded", timeout=55000)
        expect(page.locator("#country")).to_be_visible(timeout=20000)
        page.locator("#country").select_option("KE")
        page.get_by_role("button", name="Update province and city choices").click()
        page.locator("#province").select_option("Nairobi County")
        page.get_by_role("button", name="Update province and city choices").click()
        page.locator("#city").select_option("Nairobi")
        page.get_by_role("button", name="Continue to form").click()
        assert page.url.startswith(BASE + "/contact?"), "Unsafe or incorrect form return"
        assert page.locator("#city").input_value() == "Nairobi"
        print("PASS production JS-disabled country, province, city GET picker", flush=True)
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
