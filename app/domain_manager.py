"""Private, narrow Docker control API used to provision the download HTTPS proxy."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import logging
import os
from pathlib import Path
import signal
import socket
import threading

import docker
from docker.errors import APIError, ImageNotFound, NotFound

from .domain_names import normalize_public_domain

logger = logging.getLogger("domain-manager")


class DomainManager:
    def __init__(self, token: str, config_dir: Path) -> None:
        self.token = token
        self.config_dir = config_dir
        self.config_file = config_dir / "Caddyfile"
        self.client = docker.from_env(timeout=180)
        self.lock = threading.Lock()

    def _project(self) -> str:
        try:
            current = self.client.containers.get(socket.gethostname())
        except Exception as exc:
            raise RuntimeError("شناسهٔ پروژهٔ Docker پیدا نشد؛ سرویس را با Compose اجرا کن.") from exc
        project = current.labels.get("com.docker.compose.project")
        if not project:
            raise RuntimeError("برچسب پروژهٔ Compose در کانتینر مدیر دامنه موجود نیست.")
        return project

    def _network(self, project: str) -> str:
        containers = self.client.containers.list(
            filters={"label": [
                f"com.docker.compose.project={project}",
                "com.docker.compose.service=downloads-nginx",
            ]}
        )
        if not containers:
            raise RuntimeError("Nginx دانلودها پیدا نشد؛ ابتدا سرویس‌های ربات را اجرا کن.")
        networks = containers[0].attrs.get("NetworkSettings", {}).get("Networks", {})
        for name, details in networks.items():
            if "downloads-nginx" in details.get("Aliases", ()) or name.endswith("_app"):
                return name
        if networks:
            return next(iter(networks))
        raise RuntimeError("شبکهٔ داخلی Nginx دانلودها پیدا نشد.")

    def _container_name(self, project: str) -> str:
        return f"{project}_managed-download-caddy"

    @staticmethod
    def _volume_name(project: str, name: str) -> str:
        return f"{project}_{name}"

    def _ensure_volume(self, project: str, name: str) -> str:
        full_name = self._volume_name(project, name)
        try:
            self.client.volumes.get(full_name)
        except NotFound:
            self.client.volumes.create(
                name=full_name,
                labels={"com.docker.compose.project": project, "com.ytbot.managed": "true"},
            )
        return full_name

    def _current_container(self, project: str):
        try:
            return self.client.containers.get(self._container_name(project))
        except NotFound:
            return None

    def _configured_domain(self) -> str:
        try:
            first_line = self.config_file.read_text(encoding="utf-8").splitlines()[0]
        except (OSError, IndexError):
            return ""
        return first_line.removesuffix(" {").strip()

    def _start_container(
        self,
        project: str,
        domain: str,
        network: str,
        config_volume: str,
        data_volume: str,
        runtime_volume: str,
    ):
        labels = {
            "com.docker.compose.project": project,
            "com.docker.compose.service": "managed-download-caddy",
            "com.docker.compose.oneoff": "False",
            "com.ytbot.managed": "true",
            "com.ytbot.download-domain": domain,
        }
        container = self.client.containers.run(
            image="caddy:2-alpine",
            name=self._container_name(project),
            detach=True,
            restart_policy={"Name": "unless-stopped"},
            ports={"80/tcp": 80, "443/tcp": 443},
            volumes={
                config_volume: {"bind": "/etc/caddy", "mode": "ro"},
                data_volume: {"bind": "/data", "mode": "rw"},
                runtime_volume: {"bind": "/config", "mode": "rw"},
            },
            network=network,
            labels=labels,
        )
        container.reload()
        if container.status != "running":
            logs = container.logs(tail=30).decode("utf-8", errors="replace")
            raise RuntimeError(f"کانتینر Caddy بالا نیامد: {logs[-1000:]}")
        return container

    def configure(self, raw_domain: str) -> dict:
        domain = normalize_public_domain(raw_domain)
        if not domain:
            raise ValueError("نام دامنه خالی است.")
        with self.lock:
            project = self._project()
            container_name = self._container_name(project)
            existing = self._current_container(project)
            if existing and existing.status == "running" and self._configured_domain() == domain:
                return {"domain": domain, "container": container_name, "already_running": True}

            image = "caddy:2-alpine"
            try:
                self.client.images.get(image)
            except ImageNotFound:
                self.client.images.pull("caddy", "2-alpine")

            config_volume = self._ensure_volume(project, "caddy-config")
            data_volume = self._ensure_volume(project, "caddy-data")
            runtime_volume = self._ensure_volume(project, "caddy-runtime")
            network = self._network(project)
            previous_domain = self._configured_domain()
            try:
                previous_config = self.config_file.read_bytes()
            except OSError:
                previous_config = None
            was_running = bool(existing and existing.status == "running")

            self.config_dir.mkdir(parents=True, exist_ok=True)
            temp_file = self.config_dir / "Caddyfile.new"
            temp_file.write_text(
                f"{domain} {{\n    encode zstd gzip\n    reverse_proxy downloads-nginx:80\n}}\n",
                encoding="utf-8",
            )
            temp_file.replace(self.config_file)

            try:
                if existing:
                    if existing.status == "running":
                        existing.stop(timeout=10)
                    existing.remove(force=True)
                self._start_container(
                    project, domain, network, config_volume, data_volume, runtime_volume
                )
            except APIError as exc:
                failed = self._current_container(project)
                if failed:
                    try:
                        failed.remove(force=True)
                    except Exception:
                        logger.exception("Could not remove failed Caddy container")
                self._restore_config(previous_config)
                if was_running and previous_domain:
                    try:
                        self._start_container(
                            project, previous_domain, network,
                            config_volume, data_volume, runtime_volume,
                        )
                    except Exception:
                        logger.exception("Could not restore previous Caddy configuration")
                raise RuntimeError(
                    "ساخت کانتینر HTTPS ناموفق شد. آزادبودن پورت‌های ۸۰ و ۴۴۳ و دسترسی Docker را بررسی کن."
                ) from exc
            except Exception:
                failed = self._current_container(project)
                if failed:
                    try:
                        failed.remove(force=True)
                    except Exception:
                        logger.exception("Could not remove failed Caddy container")
                self._restore_config(previous_config)
                if was_running and previous_domain:
                    try:
                        self._start_container(
                            project, previous_domain, network,
                            config_volume, data_volume, runtime_volume,
                        )
                    except Exception:
                        logger.exception("Could not restore previous Caddy configuration")
                raise
            return {"domain": domain, "container": container_name, "already_running": False}

    def _restore_config(self, previous_config: bytes | None) -> None:
        if previous_config is None:
            self.config_file.unlink(missing_ok=True)
            return
        restore_file = self.config_dir / "Caddyfile.restore"
        restore_file.write_bytes(previous_config)
        restore_file.replace(self.config_file)

    def disable(self) -> dict:
        with self.lock:
            project = self._project()
            existing = self._current_container(project)
            if existing:
                try:
                    if existing.status == "running":
                        existing.stop(timeout=10)
                    existing.remove(force=True)
                except NotFound:
                    pass
            self.config_file.unlink(missing_ok=True)
            return {"domain": "", "container": self._container_name(project)}

    def restore_configured_domain(self) -> None:
        domain = self._configured_domain()
        if domain:
            self.configure(domain)

    def stop_managed_container(self) -> None:
        """Remove the proxy on Compose shutdown but retain its config for restart."""
        with self.lock:
            project = self._project()
            existing = self._current_container(project)
            if not existing:
                return
            try:
                if existing.status == "running":
                    existing.stop(timeout=5)
                existing.remove(force=True)
            except NotFound:
                pass


def _read_token() -> str:
    token_file = Path(os.getenv("DOMAIN_MANAGER_TOKEN_FILE", "/run/domain-control/domain_manager_token"))
    token = token_file.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise RuntimeError("دامنه‌منیجر توکن داخلی معتبر ندارد.")
    return token


def make_handler(manager: DomainManager):
    class Handler(BaseHTTPRequestHandler):
        server_version = "YTDomainManager/1.0"

        def _send(self, status: int, body: dict) -> None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _authorized(self) -> bool:
            supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
            return hmac.compare_digest(supplied, manager.token)

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send(200, {"ok": True})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/domain":
                self._send(404, {"error": "not found"})
                return
            if not self._authorized():
                self._send(403, {"error": "دسترسی رد شد."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 512:
                    raise ValueError("درخواست نامعتبر است.")
                body = json.loads(self.rfile.read(length))
                domain = body.get("domain") if isinstance(body, dict) else None
                if not isinstance(domain, str):
                    raise ValueError("دامنه معتبر نیست.")
                result = manager.configure(domain)
                self._send(200, {"ok": True, **result})
            except (ValueError, json.JSONDecodeError) as exc:
                self._send(400, {"error": str(exc)})
            except Exception as exc:
                logger.exception("Could not configure managed HTTPS proxy")
                self._send(503, {"error": str(exc)[:350]})

        def do_DELETE(self) -> None:
            if self.path != "/domain":
                self._send(404, {"error": "not found"})
                return
            if not self._authorized():
                self._send(403, {"error": "دسترسی رد شد."})
                return
            try:
                self._send(200, {"ok": True, **manager.disable()})
            except Exception as exc:
                logger.exception("Could not disable managed HTTPS proxy")
                self._send(503, {"error": str(exc)[:350]})

        def log_message(self, fmt, *args) -> None:
            logger.info("domain-manager %s", fmt % args)

    return Handler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    token = _read_token()
    config_dir = Path(os.getenv("CADDY_CONFIG_DIR", "/shared-caddy-config"))
    manager = DomainManager(token, config_dir)
    port = int(os.getenv("DOMAIN_MANAGER_PORT", "8088"))
    server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(manager))

    def shutdown(signum, _frame) -> None:
        logger.info("Stopping managed HTTPS proxy before shutdown")
        try:
            manager.stop_managed_container()
        except Exception:
            logger.exception("Could not stop managed HTTPS proxy")
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    threading.Thread(
        target=lambda: _restore_on_start(manager),
        name="restore-managed-caddy",
        daemon=True,
    ).start()
    logger.info("Private domain manager listening on %s", port)
    server.serve_forever()


def _restore_on_start(manager: DomainManager) -> None:
    try:
        manager.restore_configured_domain()
    except Exception:
        logger.exception("Could not restore configured HTTPS domain")


if __name__ == "__main__":
    main()
