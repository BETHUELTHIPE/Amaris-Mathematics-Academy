"""Check only whether a protected GitHub credential can read the configured Vimeo folder."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

token = os.getenv("VIMEO_TEST_CREDENTIAL", "").strip()
if not token:
    print("No Vimeo credential was available from the staging GitHub secret names checked.")
    raise SystemExit(0)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


folder = "/users/261260024/projects/31427264"
request = Request(
    f"https://api.vimeo.com{folder}?fields=uri",
    headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.vimeo.*+json;version=3.4"},
)
try:
    with build_opener(NoRedirect()).open(request, timeout=12) as response:
        result = json.load(response)
    print(f"Protected GitHub credential can read the expected Vimeo folder: {result.get('uri') == folder}.")
except HTTPError as error:
    print(f"The Vimeo folder API returned HTTP {error.code} with the protected GitHub credential.")
except (URLError, OSError, ValueError):
    print("The protected GitHub credential lookup could not complete.")
