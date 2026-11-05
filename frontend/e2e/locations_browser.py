"""Offline synthetic location checks; never send registration, enquiries or files."""
import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.getenv("E2E_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
OUT = Path("artifacts/locations")
OUT.mkdir(parents=True, exist_ok=True)
PATHS = ("/register", "/tutor/register", "/contact", "/location-test-fixture")
AXE = Path("node_modules/axe-core/axe.min.js")


def visit(page, path):
    response = page.goto(BASE + path, wait_until="networkidle")
    assert response.status == 200, (path, response.status)
    expect(page.locator("#country")).to_be_visible()


def location(page):
    country, province, city = (page.locator("#" + field) for field in ("country", "province", "city"))
    assert country.locator("option").count() == 59
    assert country.locator('option[value="US"]').count() == 0
    country.select_option("ZA")
    expect(province).to_be_enabled()
    province.select_option("Gauteng")
    city.select_option("Pretoria")
    assert city.input_value() == "Pretoria"
    province.select_option("Western Cape")
    assert city.input_value() == "", "Changing province retained an incompatible city"
    province.select_option("Gauteng")
    city.select_option("Pretoria")
    country.select_option("KE")
    expect(province).to_be_enabled()
    assert province.input_value() == "" and city.input_value() == ""
    expect(city).to_be_disabled()
    province.select_option("Nairobi County")
    city.select_option("Nairobi")
    assert city.input_value() == "Nairobi"
    province.select_option("__other__")
    page.locator("#provinceOther").fill("Synthetic region")
    city.select_option("__other__")
    assert not page.locator("#cityOther").evaluate("e => e.checkValidity()")
    expect(page.locator("#cityOther-error")).to_have_text("Please enter your city or town.")
    page.locator("#cityOther").fill("Synthetic town")
    assert page.locator("#cityOther").evaluate("e => e.checkValidity()")
    page.add_script_tag(path=str(AXE))
    violations = page.evaluate("""async () => (await axe.run(document.querySelector('#country').closest('fieldset'), {runOnly: {type:'tag', values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}})).violations""")
    assert not violations, json.dumps(violations)
    assert page.evaluate("Math.max(document.documentElement.scrollWidth,document.body.scrollWidth) <= innerWidth + 2"), "Horizontal overflow"
    values = page.locator("#country").evaluate("e => Object.fromEntries(new FormData(e.form))")
    assert values["country"] == "KE" and values["provinceOther"] == "Synthetic region" and values["cityOther"] == "Synthetic town"


with sync_playwright() as p:
    configurations = [(engine, name, {"viewport": viewport}) for engine in ("chromium", "firefox", "webkit") for name, viewport in {"narrow": {"width": 320, "height": 700}, "tablet": {"width": 834, "height": 1112}, "desktop": {"width": 1440, "height": 1000}}.items()]
    for name in ("Pixel 7", "iPhone 13"):
        descriptor = dict(p.devices[name])
        engine = descriptor.pop("default_browser_type")
        configurations.append((engine, name, descriptor))
    for engine, name, options in configurations:
        browser = getattr(p, engine).launch()
        context = browser.new_context(**options, locale="en-ZA", timezone_id="Africa/Johannesburg")
        posts = []
        def block(route):
            if route.request.method == "POST":
                posts.append(route.request.url)
                route.abort()
            else:
                route.continue_()
        context.route("**/*", block)
        page = context.new_page()
        page.set_default_timeout(30000)
        try:
            for path in PATHS:
                visit(page, path)
                location(page)
            assert not posts, posts
            page.screenshot(path=str(OUT / f"{engine}-{name.replace(' ', '-')}.png"), full_page=True)
            print(f"PASS {engine}/{name}: all four forms, dependent reset, Other names, separate posted values, axe WCAG and overflow", flush=True)
        except Exception:
            page.screenshot(path=str(OUT / f"failure-{engine}-{name.replace(' ', '-')}.png"), full_page=True)
            raise
        finally:
            context.close()
            browser.close()

    browser = p.chromium.launch()
    context = browser.new_context()
    page = context.new_page()
    visit(page, "/contact")
    failures = []
    def unavailable(route):
        failures.append(route.request.url)
        if len(failures) == 1:
            route.fulfill(status=503, body="Unavailable")
        else:
            route.continue_()
    page.route("**/data/locations/KE.json*", unavailable)
    page.locator("#country").select_option("KE")
    expect(page.get_by_role("button", name="Try again", exact=True)).to_be_visible()
    page.get_by_role("button", name="Try again", exact=True).click()
    expect(page.locator("#province")).to_be_enabled()
    page.locator("#province").select_option("Nairobi County")
    page.locator("#city").select_option("Nairobi")
    page.reload(wait_until="networkidle")
    expect(page.locator("#city")).to_have_value("Nairobi")
    print("PASS retry after failed lookup and restored country/province/city draft", flush=True)
    context.close()

    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    visit(page, "/locations?returnTo=/contact")
    page.locator("#country").select_option("KE")
    page.get_by_role("button", name="Update province and city choices").click()
    page.locator("#province").select_option("Nairobi County")
    page.get_by_role("button", name="Update province and city choices").click()
    page.locator("#city").select_option("Nairobi")
    page.get_by_role("button", name="Continue to form").click()
    assert page.url.startswith(BASE + "/contact?")
    assert page.locator("#city").input_value() == "Nairobi"
    visit(page, "/locations?returnTo=https://evil.example.test&country=KE&province=__other__&city=__other__")
    page.locator("#provinceOther").fill("Synthetic region")
    page.locator("#cityOther").fill("Synthetic town")
    page.get_by_role("button", name="Continue to form").click()
    assert page.url.startswith(BASE + "/register?")
    assert page.locator("#cityOther").input_value() == "Synthetic town"
    print("PASS JavaScript-disabled country/region/city picker, Other names and safe return URL", flush=True)
    context.close()
    browser.close()
