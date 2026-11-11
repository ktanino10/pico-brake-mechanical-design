"""Loopback-only preview; never serve .git, directories, symlinks or arbitrary paths."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
import argparse
import hashlib
import json
import mimetypes
import shutil

from public_files import WEB_FILES

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "/pico-brake-mechanical-design/"


class PublicHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.serve(head=False)

    def do_HEAD(self):
        self.serve(head=True)

    def serve(self, head):
        path = unquote(urlsplit(self.path).path)
        if path.startswith(PREFIX):
            name = path[len(PREFIX):]
        else:
            name = path.removeprefix("/")
        if not name:
            name = "index.html"
        target = ROOT / name
        if name not in WEB_FILES or target.is_symlink() or not target.resolve().is_relative_to(ROOT):
            self.send_error(404, "Not a public payload")
            return
        if not target.is_file():
            self.send_error(404, "Public file is not ready")
            return
        if name.startswith("downloads/"):
            try:
                release = json.loads((ROOT / "data/checksums.json").read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                self.send_error(503, "CAD validation manifest is unavailable")
                return
            entry = next((item for item in release.get("files", []) if item.get("path") == name), None)
            if release.get("downloads_ready") is not True or entry is None:
                self.send_error(503, "CAD downloads paused pending independent validation")
                return
            if hashlib.sha256(target.read_bytes()).hexdigest() != entry["sha256"]:
                self.send_error(503, "CAD file changed after validation")
                return
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if name.endswith((".js", ".mjs")):
            content_type = "text/javascript"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(target.stat().st_size))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if not head:
            with target.open("rb") as stream:
                shutil.copyfileobj(stream, self.wfile)

    def log_message(self, format_string, *args):
        if len(args) > 1 and str(args[1]) not in {"200", "304"}:
            print("Preview request:", format_string % args, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), PublicHandler)
    print(f"Public-only preview: http://127.0.0.1:{server.server_port}{PREFIX}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
