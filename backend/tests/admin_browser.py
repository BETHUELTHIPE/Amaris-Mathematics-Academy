"""Real-browser admin acceptance using temporary SQLite and synthetic local users."""

import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BACKEND = Path(__file__).resolve().parent.parent


def login(page, origin, username, password, *, keyboard=False):
    page.goto(origin + "/admin/")
    page.get_by_label("Username", exact=True).fill(username)
    page.get_by_label("Password", exact=True).fill(password)
    if keyboard:
        page.get_by_label("Password", exact=True).press("Enter")
    else:
        page.get_by_role("button", name="Sign in to workspace").click()
    expect(page.locator(".amaris-welcome")).to_be_visible()


def assert_desktop_shell(page):
    # Read settled layout, including the framework's sidebar transitions.
    page.wait_for_function("""() => {
            const sidebar = document.querySelector('.main-sidebar').getBoundingClientRect();
            return ['.content-wrapper', '.main-header', '.main-footer'].every(selector =>
                document.querySelector(selector).getBoundingClientRect().left >= sidebar.right - 1);
        }""")


def main():
    artifacts = Path(os.getenv("ADMIN_BROWSER_ARTIFACT_DIR", tempfile.mkdtemp(prefix="amaris-admin-visuals-")))
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="amaris-admin-qa-") as root:
        env = {key: value for key, value in os.environ.items() if key in {"PATH", "LD_LIBRARY_PATH"}}
        password = secrets.token_urlsafe(24)
        env.update(
            DJANGO_SETTINGS_MODULE="amaris_cms.settings",
            DJANGO_DEBUG="true",
            DJANGO_SECRET_KEY=secrets.token_urlsafe(48),
            DJANGO_ALLOWED_HOSTS="127.0.0.1,localhost",
            DATABASE_URL="sqlite:///" + str(Path(root) / "admin-qa.sqlite3"),
            SUPABASE_DATABASE_REQUIRED="false",
            AMARIS_COLOCATE_NOTIFICATIONS="false",
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            CELERY_BROKER_URL="memory://",
            CELERY_RESULT_BACKEND="cache+memory://",
            DJANGO_CACHE_URL="redis://127.0.0.1:9/0",
            DJANGO_PUBLIC_CACHE_URL="redis://127.0.0.1:9/1",
            ADMIN_QA_PASSWORD=password,
        )
        subprocess.run(
            [sys.executable, "manage.py", "migrate", "--noinput"],
            cwd=BACKEND,
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        seed = """
import json,os,django
django.setup()
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory
User=get_user_model()
User.objects.create_superuser('academy-qa','qa@example.invalid',os.environ['ADMIN_QA_PASSWORD'],first_name='Alex')
editor=User.objects.create_user('course-editor','editor@example.invalid',os.environ['ADMIN_QA_PASSWORD'],is_staff=True)
editor.user_permissions.add(Permission.objects.get(codename='view_course',content_type__app_label='content'))
request=RequestFactory().get('/admin/')
request.user=editor
print(json.dumps(sorted(model['admin_url'] for app in admin.site.get_app_list(request)
    for model in app['models'] if model.get('admin_url'))))
"""
        authorized_editor_urls = json.loads(
            subprocess.check_output([sys.executable, "-c", seed], cwd=BACKEND, env=env, text=True)
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        with (Path(root) / "server.log").open("w") as output:
            server = subprocess.Popen(
                [sys.executable, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"],
                cwd=BACKEND,
                env=env,
                stdout=output,
                stderr=output,
            )
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(origin + "/health/live/", timeout=1) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise AssertionError("Local admin preview did not start")
                with sync_playwright() as p:
                    options = {"headless": True}
                    if os.getenv("ADMIN_BROWSER_EXECUTABLE"):
                        options["executable_path"] = os.environ["ADMIN_BROWSER_EXECUTABLE"]
                    browser = p.chromium.launch(**options)
                    context = browser.new_context(viewport={"width": 1440, "height": 1000})
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(origin + "/admin/login/")
                    page.screenshot(path=str(artifacts / "admin-login.png"), full_page=True, animations="disabled")
                    login(page, origin, "academy-qa", password)
                    expect(page.get_by_role("heading", name="Welcome back, Alex.")).to_be_visible()
                    expect(page.get_by_role("button", name="Toggle navigation")).to_be_visible()
                    assert_desktop_shell(page)
                    expect(page.locator(".amaris-model-link").first).to_have_css("color", "rgb(66, 84, 108)")
                    page.screenshot(path=str(artifacts / "admin-desktop.png"), full_page=True, animations="disabled")
                    page.get_by_label("Find a management tool").fill("invoice")
                    expect(page.locator("[data-tool-name]:visible")).to_have_count(1)
                    expect(page.get_by_role("status")).to_contain_text("1 management tool found")
                    page.get_by_label("Find a management tool").fill("not-a-real-tool")
                    expect(page.locator("[data-tool-empty]")).to_be_visible()
                    page.get_by_label("Find a management tool").fill("")
                    page.emulate_media(reduced_motion="reduce")
                    assert (
                        page.locator(".amaris-welcome").evaluate("el => getComputedStyle(el).animationName") == "none"
                    )
                    for width in (390, 768, 1440):
                        page.set_viewport_size({"width": width, "height": 900})
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= window.innerWidth + 1"
                        ), f"Overview overflow at {width}px"
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.screenshot(path=str(artifacts / "admin-mobile.png"))
                    page.set_viewport_size({"width": 1440, "height": 1000})
                    page.locator('.amaris-model-link[href="/admin/content/course/"]').click()
                    expect(page.locator("#changelist")).to_be_visible()
                    page.goto(origin + "/admin/content/course/add/")
                    expect(page.locator("#course_form")).to_be_visible()
                    assert_desktop_shell(page)
                    expect(page.locator('[name="_save"]')).to_have_css("color", "rgb(255, 255, 255)")
                    page.screenshot(path=str(artifacts / "admin-editor.png"), full_page=True)
                    assert not errors, errors
                    context.close()
                    restricted = browser.new_context(viewport={"width": 390, "height": 844}, java_script_enabled=False)
                    editor_page = restricted.new_page()
                    login(editor_page, origin, "course-editor", password, keyboard=True)
                    # Existing read-only admin overrides can grant access without a model permission.
                    # Compare with Django's native app list rather than assuming exactly one tool.
                    expect(editor_page.locator(".amaris-model-link")).to_have_count(len(authorized_editor_urls))
                    assert (
                        sorted(
                            editor_page.locator(".amaris-model-link").evaluate_all(
                                "links => links.map(link => link.getAttribute('href'))"
                            )
                        )
                        == authorized_editor_urls
                    )
                    expect(editor_page.locator('.amaris-model-link[href="/admin/content/course/"]')).to_be_visible()
                    assert editor_page.locator('a[href*="/monitoring/"]').count() == 0
                    assert editor_page.locator('a[href="/admin/content/payment/"]').count() == 0
                    expect(editor_page.locator("[data-tool-search]")).to_be_hidden()
                    editor_page.screenshot(path=str(artifacts / "admin-restricted-no-js.png"), animations="disabled")
                    editor_page.locator('.amaris-model-link[href="/admin/content/course/"]').press("Enter")
                    expect(editor_page.locator("#changelist")).to_be_visible()
                    assert editor_page.goto(origin + "/admin/content/payment/").status == 403
                    restricted.close()
                    browser.close()
                print(
                    "PASS admin login, desktop/mobile/tablet, filtering, reduced motion, editors and no-JS permissions"
                )
                print(f"Visual evidence: {artifacts}")
            finally:
                server.send_signal(signal.SIGTERM)
                server.wait(timeout=10)


if __name__ == "__main__":
    main()
