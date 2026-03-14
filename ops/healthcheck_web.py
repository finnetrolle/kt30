"""
Container-local readiness probe for the web service.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    url = os.getenv("WEB_HEALTHCHECK_URL", "http://127.0.0.1:8000/ready")
    timeout = float(os.getenv("WEB_HEALTHCHECK_TIMEOUT_SECONDS", "5"))

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            payload = json.loads(body)
            if response.status != 200 or payload.get("status") != "ready":
                print(f"web not ready: status={response.status} payload={payload}")
                return 1
    except urllib.error.URLError as exc:
        print(f"web readiness probe failed: {exc}")
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"web readiness probe returned invalid JSON: {exc}")
        return 1

    print("web ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
