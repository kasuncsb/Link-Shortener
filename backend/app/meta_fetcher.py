"""
Async OG / meta-tag fetcher.
Returns a dict with: title, description, image, favicon, domain
Falls back gracefully on timeout / parse errors.
"""
import asyncio
import httpx
from urllib.parse import urlparse
from urllib.parse import urljoin
import ipaddress
from bs4 import BeautifulSoup
from typing import Optional

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

TIMEOUT = 10.0  # seconds


def _is_private_ip(addr: str) -> bool:
    """Check if a resolved IP address is private/reserved."""
    try:
        ip = ipaddress.ip_address(addr)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )
    except ValueError:
        return True


async def _is_public_target(url: str) -> bool:
    """Allow only public internet hosts to avoid SSRF to local/private networks."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return False
        host_l = host.lower()
        if host_l in {"localhost", "127.0.0.1", "::1"}:
            return False

        # Direct IP host
        try:
            ip = ipaddress.ip_address(host_l)
            return not _is_private_ip(host_l)
        except ValueError:
            pass

        # DNS host: resolve asynchronously to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(host, None)
        if not infos:
            return False
        for info in infos:
            addr = info[4][0]
            if _is_private_ip(addr):
                return False
        return True
    except Exception:
        return False


def _extract(soup: BeautifulSoup, url: str) -> dict:
    def og(prop: str) -> Optional[str]:
        tag = soup.find("meta", property=f"og:{prop}")
        if tag and tag.get("content"):  # type: ignore[union-attr]
            return str(tag["content"]).strip() or None  # type: ignore[call-overload]
        return None

    def tw(name: str) -> Optional[str]:
        tag = soup.find("meta", attrs={"name": f"twitter:{name}"})
        if tag and tag.get("content"):  # type: ignore[union-attr]
            return str(tag["content"]).strip() or None  # type: ignore[call-overload]
        return None

    def meta_name(name: str) -> Optional[str]:
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):  # type: ignore[union-attr]
            return str(tag["content"]).strip() or None  # type: ignore[call-overload]
        return None

    parsed = urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")

    title = (
        og("title")
        or tw("title")
        or (soup.title.string.strip() if soup.title and soup.title.string else None)
        or domain
    )

    description = (
        og("description")
        or tw("description")
        or meta_name("description")
    )
    if description:
        description = description[:200]

    image = (
        og("image")
        or tw("image:src")
        or tw("image")
        or meta_name("image")
    )

    # Strict OG presence check (explicit Open Graph fields only).
    has_og_meta = bool(
        og("title")
        or og("description")
        or og("image")
    )

    # Resolve relative image URL
    if image:
        image = urljoin(f"{parsed.scheme}://{parsed.netloc}/", image)

    # Favicon: prefer link[rel~=icon], fall back to /favicon.ico
    favicon = None
    for rel in ("apple-touch-icon", "shortcut icon", "icon"):
        tag = soup.find("link", rel=lambda r, _r=rel: r and _r in r)  # type: ignore[arg-type]
        if tag and tag.get("href"):  # type: ignore[union-attr]
            href = str(tag["href"])  # type: ignore[call-overload]
            if href.startswith("//"):
                href = f"{parsed.scheme}:{href}"
            elif href.startswith("/"):
                href = f"{parsed.scheme}://{parsed.netloc}{href}"
            favicon = href
            break
    if not favicon:
        favicon = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"

    return {
        "title": title,
        "description": description,
        "image": image,
        "favicon": favicon,
        "domain": domain,
        "has_og_meta": has_og_meta,
    }


async def fetch_meta(url: str) -> dict:
    """Fetch OG metadata for a URL. Returns empty-ish dict on failure."""
    try:
        if not await _is_public_target(url):
            raise ValueError("Target host is not public")
        async with httpx.AsyncClient(
            headers=HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if "html" not in ct:
                raise ValueError("Not HTML")
            soup = BeautifulSoup(resp.text, "html.parser")
            data = _extract(soup, str(resp.url))
            data["fetched_url"] = str(resp.url)
            return data
    except Exception:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().removeprefix("www.")
        return {
            "title": domain or url,
            "description": None,
            "image": None,
            "favicon": f"{parsed.scheme}://{parsed.netloc}/favicon.ico",
            "domain": domain,
            "has_og_meta": False,
        }
