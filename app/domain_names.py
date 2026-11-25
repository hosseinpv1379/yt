"""Validation shared by the admin flow and the HTTPS container manager."""
import ipaddress
import re


_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def normalize_public_domain(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    if raw.endswith(".."):
        raise ValueError("نام دامنه معتبر نیست؛ فقط یک نقطهٔ پایانی مجاز است.")
    if raw.endswith("."):
        raw = raw[:-1]
    if not raw:
        raise ValueError("یک دامنهٔ عمومی مثل files.example.com وارد کن.")
    if "://" in raw or "/" in raw or "*" in raw or "@" in raw:
        raise ValueError("فقط نام دامنه را بفرست؛ نمونه: files.example.com")
    try:
        domain = raw.encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError) as exc:
        raise ValueError("نام دامنه معتبر نیست.") from exc
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        pass
    else:
        raise ValueError("برای SSL خودکار، دامنه بفرست؛ IP به‌تنهایی گواهی عمومی نمی‌گیرد.")
    if "." not in domain or len(domain) > 253 or domain.endswith((".local", ".localhost")):
        raise ValueError("یک دامنهٔ عمومی مثل files.example.com وارد کن.")
    labels = domain.split(".")
    if any(len(label) > 63 or not _LABEL.fullmatch(label) for label in labels):
        raise ValueError("نام دامنه معتبر نیست؛ فاصله، پورت و مسیر وارد نکن.")
    if not re.fullmatch(r"[a-z]{2,}|xn--[a-z0-9-]{2,}", labels[-1]):
        raise ValueError("پسوند دامنه معتبر نیست.")
    return domain
