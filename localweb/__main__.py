"""Start the local-only web application with ``python -m localweb``."""
import argparse
import hmac
import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import models, settings
from .service import LocalService

STATIC = Path(__file__).parent / "static"


def make_server(port=0):
    service = LocalService()
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return  # Do not put request content or tokens in logs.

        def valid_host(self):
            return self.headers.get("Host", "") == f"127.0.0.1:{self.server.server_port}"

        def respond(self, status, data, content_type="application/json; charset=utf-8"):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.valid_host():
                return self.respond(403, {"error": "invalid host"})
            path = urlsplit(self.path).path
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8")}
            if path in files:
                name, mime = files[path]
                body = (STATIC / name).read_bytes()
                if path == "/":
                    body = body.replace(b"__SESSION_TOKEN__", token.encode("ascii"))
                return self.respond(200, body, mime)
            if path == "/api/status":
                return self.respond(200, service.status())
            if path == "/api/settings":
                try:
                    prefs = settings.load_preferences()
                    return self.respond(200, {"preferences": prefs, "models": list(models.MODELS)})
                except Exception:
                    return self.respond(500, {"error": "خواندن تنظیمات ممکن نشد."})
            return self.respond(404, {"error": "not found"})

        def do_POST(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            provided = self.headers.get("X-Session-Token", "")
            if not self.valid_host() or self.headers.get("Origin") != origin or not hmac.compare_digest(provided, token):
                return self.respond(403, {"error": "درخواست نامعتبر است."})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0 or size > 65536 or self.headers.get_content_type() != "application/json":
                    raise ValueError("درخواست نامعتبر است.")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("درخواست نامعتبر است.")
                path = urlsplit(self.path).path
                if path == "/api/settings":
                    incoming = data.get("preferences", {})
                    keys = data.get("keys", {})
                    if not isinstance(incoming, dict) or not isinstance(keys, dict):
                        raise ValueError("تنظیمات معتبر نیست.")
                    prefs = settings.load_preferences()
                    prefs.update({k: str(v) for k, v in incoming.items() if k in settings.DEFAULTS})
                    if prefs["provider"] not in {"openai", "openrouter"}:
                        raise ValueError("ارائه‌دهنده معتبر نیست.")
                    settings.pipeline_settings(prefs, {}, Path(prefs["output_dir"]))
                    if not 0 <= int(prefs["original_audio_percent"]) <= 100:
                        raise ValueError("درصد صدای اصلی معتبر نیست.")
                    for provider in ("openai", "openrouter"):
                        value = keys.get(provider, "")
                        if not isinstance(value, str):
                            raise ValueError("کلید معتبر نیست.")
                        if value:
                            settings.set_key(provider, value)
                    settings.save_preferences(prefs)
                elif path == "/api/start":
                    service.start(data.get("kind"), data.get("source"))
                elif path == "/api/cancel":
                    service.cancel.set()
                else:
                    return self.respond(404, {"error": "not found"})
                return self.respond(200, {"ok": True})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return self.respond(400, {"error": str(exc)})
            except Exception:
                return self.respond(500, {"error": "عملیات انجام نشد؛ تنظیمات یا مخزن امن سیستم را بررسی کنید."})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = make_server(args.port)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"YT Local: {url}", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
