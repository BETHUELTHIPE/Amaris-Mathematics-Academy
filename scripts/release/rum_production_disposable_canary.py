"""One known, disposable RUM canary. Must be deleted from production histograms.

No identity, IP, cookies, payment details or raw paths in the POST body.
The route 'other-public' is not emitted by the browser classifier, and the
out-of-range CLS value is reserved for cleanup of this exact canary.
"""
import json
import time
import urllib.error
import urllib.request

url = "https://amaris-mathematics-academy-live-students.onrender.com/api/field-vitals"
origin = "https://amaris-mathematics-academy-live-students.onrender.com"
body = json.dumps({"records": [
    {"name": "CLS", "value": 9.99, "route": "other-public",
     "device": "tablet", "network": "slow-2g"}
]}, separators=(",", ":")).encode()

for i in range(4):
    request = urllib.request.Request(
        url, method="POST", data=body,
        headers={"Origin": origin, "Content-Type": "application/json",
                 "User-Agent": "Amaris-disposable-RUM-release-canary/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=24) as response:
            status = response.status
    except urllib.error.HTTPError as err:
        status = err.code
    except OSError:
        status = 0
    if status == 204:
        print("PASS production Next -> token-authenticated Django -> histogram HTTP 204")
        print("CLEANUP REQUIRED: exact artificial CLS 9.99 other-public/tablet/slow-2g")
        break
    if status == 503 and i < 3:
        time.sleep(8)
        continue
    raise SystemExit(f"BLOCK: positive RUM forwarding expected HTTP 204, received {status}")
else:
    raise SystemExit("BLOCK: forwarding timed out")
