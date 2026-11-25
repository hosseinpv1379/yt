"""PostgreSQL backup creation for scheduled delivery to the configured admin."""
import asyncio
from pathlib import Path
import os

from sqlalchemy.engine import make_url


async def create_database_backup(database_url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("پشتیبان‌گیری خودکار فقط برای PostgreSQL پیکربندی شده است.")
    command = ["pg_dump", "--no-owner", "--format=custom", "--compress=6"]
    if url.host:
        command += ["--host", url.host]
    if url.port:
        command += ["--port", str(url.port)]
    if url.username:
        command += ["--username", url.username]
    command += ["--dbname", url.database or ""]
    command += ["--file", str(destination)]
    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = url.password
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    _, stderr = await process.communicate()
    if process.returncode:
        raise RuntimeError(stderr.decode("utf-8", errors="replace")[-1500:] or "pg_dump failed")
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("pg_dump فایل خالی ساخت.")
    return destination
