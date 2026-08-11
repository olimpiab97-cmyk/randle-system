import argparse
import json
import os
import sys

import requests


def redacted_exception_detail(exc, secret=None):
    detail = str(exc)
    return detail.replace(secret, "<redacted>") if secret else detail


def request_public_json(
    url,
    timeout_seconds,
    method="GET",
    payload=None,
    query_token=None,
):
    session = requests.Session()
    session.trust_env = False
    request_kwargs = {
        "timeout": (timeout_seconds, timeout_seconds),
        "verify": True,
        "headers": {"ngrok-skip-browser-warning": "1"},
    }
    if method == "POST":
        request_kwargs["json"] = payload
    if query_token:
        request_kwargs["params"] = {"token": query_token}
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
    parser.add_argument("--query-token-env")
    args = parser.parse_args()
    query_token = None
    try:
        if args.query_token_env:
            query_token = str(os.getenv(args.query_token_env, "") or "")
            if not query_token:
                raise RuntimeError(f"required credential environment is missing: {args.query_token_env}")
        payload = None
        if args.json_file:
            with open(args.json_file, "r", encoding="utf-8") as file:
                payload = json.load(file)
        result = request_public_json(
            args.url,
            args.timeout_seconds,
            method=args.method,
            payload=payload,
            query_token=query_token,
        )
    except Exception as exc:
        detail = redacted_exception_detail(exc, query_token)
        result = {"ok": False, "error": f"{type(exc).__name__}:{detail}"}
        print(json.dumps(result, separators=(",", ":")))
        return 1
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
