"""Simple HTTP server for graph-preview.html with POST /save-layout support."""

import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
EXPORT_PATH = os.path.join(STATIC_DIR, "layout-export.json")
PORT = 8765


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_POST(self):
        if self.path == "/save-layout":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)
            with open(EXPORT_PATH, "w") as f:
                json.dump(data, f, indent=2)
            print(f"[save-layout] Written to {EXPORT_PATH}")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b"saved")
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        # Suppress GET noise, keep POST logs
        if args and str(args[1]) not in ("200", "304"):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    print(f"Graph preview: http://localhost:{PORT}/graph-preview.html")
    print(f"Layout export: {EXPORT_PATH}")
    HTTPServer(("", PORT), Handler).serve_forever()
