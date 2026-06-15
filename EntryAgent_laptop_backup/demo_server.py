"""Read-only HTTP server for the Entry Agent demo harness."""

from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from demo_harness import evaluate_fixture_file, list_fixture_entries, list_fixtures


ROOT_DIR = Path(__file__).resolve().parent.parent


class EntryAgentDemoHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/entry-agent-demo/index":
            self._send_json({"fixtures": list_fixtures(), "entries": list_fixture_entries()})
            return
        prefix = "/api/entry-agent-demo/case/"
        if parsed.path.startswith(prefix):
            name = unquote(parsed.path[len(prefix) :])
            try:
                self._send_json(evaluate_fixture_file(name))
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=404)
            return
        if parsed.path in {"/", "/entry-agent-demo"}:
            self.path = "/entry_agent_demo.html"
        super().do_GET()

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), EntryAgentDemoHandler)
    try:
        print(f"Entry Agent demo harness: http://{host}:{port}/entry_agent_demo.html", flush=True)
    except OSError:
        pass
    server.serve_forever()


if __name__ == "__main__":
    run()
