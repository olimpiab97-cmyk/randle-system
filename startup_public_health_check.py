import argparse
import json
import sys

import requests


def request_public_json(url, timeout_seconds, method="GET", payload=None):
    session = requests.Session()
    session.trust_env = False
    request_kwargs = {
        "timeout": (timeout_seconds, timeout_seconds),
        "verify": True,
        "headers": {"ngrok-skip-browser-warning": "1"},
    }
    if method == "POST":
        request_kwargs["json"] = payload
    response = session.request(method, url, **request_kwargs)
    response.raise_for_status()
    return {
        "ok": True,
        "status_code": response.status_code,
        "health": response.json(),
    }


def check_public_health(url, timeout_seconds):
    return request_public_json(url, timeout_seconds)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--method", choices=("GET", "POST"), default="GET")
    parser.add_argument("--json-file")
    args = parser.parse_args()
    try:
        payload = None
        if args.json_file:
            with open(args.json_file, "r", encoding="utf-8") as file:
                payload = json.load(file)
        result = request_public_json(
            args.url,
            args.timeout_seconds,
            method=args.method,
            payload=payload,
        )
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}:{exc}"}
        print(json.dumps(result, separators=(",", ":")))
        return 1
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
