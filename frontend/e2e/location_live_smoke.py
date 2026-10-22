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

if os.getenv("LOCATION_LAYOUT_ONLY") == "true":
    import json
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in (320, 390, 412, 640, 834, 1440):
            context = browser.new_context(viewport={"width": width, "height": 900})
            context.route("**/*", lambda route: route.abort() if route.request.method == "POST" else route.continue_())
            page = context.new_page()
            page.add_init_script("window.layoutShifts=[]; new PerformanceObserver(list => {for(const e of list.getEntries()) if(!e.hadRecentInput) window.layoutShifts.push(e.value)}).observe({type:'layout-shift',buffered:true})")
            page.goto(SITE + "/", wait_until="networkidle")
            print("HOME_INITIAL", width, json.dumps(page.locator(".home-shell > section").evaluate_all("nodes => nodes.map(e => ({classes:e.className, height:Math.round(e.getBoundingClientRect().height), visible:e.checkVisibility({contentVisibilityAuto:true})}))")), flush=True)
            for section in page.locator(".home-shell > section").all():
                section.scroll_into_view_if_needed()
            page.evaluate("window.scrollTo(0,0)")
            print("HOME_LAYOUT", width, json.dumps(page.locator(".home-shell > section").evaluate_all("nodes => nodes.map(e => ({classes:e.className, height:Math.round(e.getBoundingClientRect().height), top:Math.round(e.getBoundingClientRect().top+scrollY)}))")), flush=True)
            print("HOME_SCROLL_CLS", width, page.evaluate("window.layoutShifts.reduce((a,b)=>a+b,0)"), flush=True)
            page.screenshot(path=str(OUT / ("home-layout-" + str(width) + ".png")), full_page=True)
            context.close()
        browser.close()
    raise SystemExit(0)

with sync_playwright() as p:
    for engine in ("chromium", "firefox", "webkit"):
        browser = getattr(p, engine).launch()
        for width in (390, 1440):
            context = browser.new_context(viewport={"width": width, "height": 900},
                                          locale="en-ZA", timezone_id="Africa/Johannesburg")
            posts = []
            def guard(route):
                if route.request.method == "POST":
                    from urllib.parse import urlsplit
                    target = urlsplit(route.request.url).path
                    posts.append(target)
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
                expect(page.locator("#cityOther")).to_have_value("Synthetic town")
                print("Other input state", engine, width, path, page.locator("#cityOther").evaluate("e => ({value:e.value, message:e.validationMessage, customError:e.validity.customError, missing:e.validity.valueMissing})"), flush=True)
                page.screenshot(path=str(OUT / ("before-validity-" + engine + "-" + str(width) + path.replace("/", "-") + ".png")), full_page=True)
                assert page.locator("#cityOther").evaluate("e => e.checkValidity()")
                page.reload(wait_until="networkidle")
                expect(page.locator("#provinceOther")).to_have_value("Synthetic region")
                expect(page.locator("#cityOther")).to_have_value("Synthetic town")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
                page.screenshot(path=str(OUT / (engine + "-" + str(width) + path.replace("/", "-") + ".png")), full_page=True)
                print("PASS " + engine + "/" + str(width) + path + ": reset, Other validation, draft recovery, responsive", flush=True)
            print("Blocked POST paths", sorted(set(posts)), flush=True)
            assert not [path for path in posts if path not in {"/api/field-vitals", "/api/field-vitals/"}], "Unexpected form submission blocked: " + repr(sorted(set(posts)))
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
