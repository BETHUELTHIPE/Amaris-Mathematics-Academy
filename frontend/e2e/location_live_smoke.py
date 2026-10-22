"""Read-only checks of deployed public location forms; block every browser POST."""
import os
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

SITE = os.environ["LOCATION_SITE"].rstrip("/")
API = os.environ["LOCATION_API"].rstrip("/")
OUT = Path("artifacts/location-live")
OUT.mkdir(parents=True, exist_ok=True)
for path in ("/health/live/", "/health/ready/"):
    with urlopen(API + path, timeout=30) as response:
        assert response.status == 200
    print("PASS backend " + path, flush=True)

with sync_playwright() as p:
    for engine in ("chromium", "firefox", "webkit"):
        browser = getattr(p, engine).launch()
        for width in (390, 1440):
            context = browser.new_context(viewport={"width": width, "height": 900},
                                          locale="en-ZA", timezone_id="Africa/Johannesburg")
            posts = []
            def guard(route):
                if route.request.method == "POST":
                    posts.append(route.request.url)
                    route.abort()
                else:
                    route.continue_()
            context.route("**/*", guard)
            page = context.new_page()
            page.set_default_timeout(30000)
            for path in ("/register", "/tutor/register", "/contact"):
                response = page.goto(SITE + path, wait_until="networkidle")
                assert response.status == 200
                country, province, city = (page.locator("#" + x) for x in ("country", "province", "city"))
                expect(country).to_be_visible()
                assert country.locator("option").count() == 59
                country.select_option("ZA")
                expect(province.locator('option[value="Gauteng"]')).to_have_count(1)
                province.select_option("Gauteng")
                city.select_option("Pretoria")
                province.select_option("Western Cape")
                assert city.input_value() == ""
                country.select_option("KE")
                expect(province.locator('option[value="Nairobi County"]')).to_have_count(1)
                assert province.input_value() == "" and city.input_value() == ""
                province.select_option("Nairobi County")
                city.select_option("Nairobi")
                province.select_option("__other__")
                page.locator("#provinceOther").fill("Synthetic region")
                city.select_option("__other__")
                assert not page.locator("#cityOther").evaluate("e => e.checkValidity()")
                expect(page.locator("#cityOther-error")).to_have_text("Please enter your city or town.")
                page.locator("#cityOther").fill("Synthetic town")
                assert page.locator("#cityOther").evaluate("e => e.checkValidity()")
                page.reload(wait_until="networkidle")
                expect(page.locator("#provinceOther")).to_have_value("Synthetic region")
                expect(page.locator("#cityOther")).to_have_value("Synthetic town")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
                page.screenshot(path=str(OUT / (engine + "-" + str(width) + path.replace("/", "-") + ".png")), full_page=True)
                print("PASS " + engine + "/" + str(width) + path + ": reset, Other validation, draft recovery, responsive", flush=True)
            assert not posts, "Unexpected submission blocked"
            context.close()
        browser.close()
    browser = p.chromium.launch()
    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    page.goto(SITE + "/locations?returnTo=/contact&country=KE&province=__other__&city=__other__")
    page.locator("#provinceOther").fill("Synthetic region")
    page.locator("#cityOther").fill("Synthetic town")
    page.get_by_role("button", name="Continue to form", exact=True).click()
    assert page.url.startswith(SITE + "/contact?")
    expect(page.locator("#cityOther")).to_have_value("Synthetic town")
    print("PASS JavaScript-disabled Other names return to contact", flush=True)
    context.close()
    browser.close()
print("PASS live read-only location smoke; no registrations, enquiries, emails or payments submitted", flush=True)
