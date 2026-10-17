import hashlib
import ipaddress
import socket
import re
from urllib.parse import urlparse
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


class PageCheckError(RuntimeError):
    """A fetch failure that must not be interpreted as a content change."""

    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category

def safe_public_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Enter a complete http:// or https:// URL.")
    host = parsed.hostname.lower()
    if host in ("localhost",) or host.endswith(".local"):
        raise ValueError("Local/private destinations are not allowed.")
    try:
        addresses = socket.getaddrinfo(host, None)
        for item in addresses:
            ip = ipaddress.ip_address(item[4][0])
            if not ip.is_global:
                raise ValueError("This URL resolves to a non-public IP address.")
    except socket.gaierror:
        raise ValueError("Could not resolve this hostname.")
    return url.strip()

def clean_text(html: str, include_selector: str = "", ignore_selector: str = "") -> str:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg", "canvas", "iframe"]):
        node.decompose()

    # Optional watch region. If the selector is invalid or absent, fail clearly.
    if include_selector:
        try:
            chosen = soup.select_one(include_selector)
        except Exception as e:
            raise ValueError(f"Invalid watch CSS selector: {e}")
        if chosen is None:
            raise ValueError(f"Watch selector matched no element: {include_selector}")
        soup = BeautifulSoup(str(chosen), "html.parser")

    if ignore_selector:
        try:
            for node in soup.select(ignore_selector):
                node.decompose()
        except Exception as e:
            raise ValueError(f"Invalid ignore CSS selector: {e}")

    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    # Common volatile date/time patterns are not blindly removed; users can ignore
    # the exact region via CSS selector to avoid deleting meaningful dates.
    return text.strip()

def check_page(url: str, screenshot_path: str, include_selector: str = "",
               ignore_selector: str = "", sensitivity: int = 3) -> dict:
    safe_public_url(url)
    Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1365, "height": 900}, device_scale_factor=1)
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=20000)
            if response is not None and response.status >= 500:
                raise PageCheckError("OUTAGE", f"The website returned HTTP {response.status}.")
            if response is not None and response.status >= 400 and response.status not in (403, 429):
                raise PageCheckError("HTTP ERROR", f"The website returned HTTP {response.status}.")
            page.wait_for_timeout(900)
            title = page.title()
            html = page.content()
            challenge_text = f"{title} {BeautifulSoup(html, 'html.parser').get_text(' ', strip=True)}".lower()
            captcha_markers = (
                "captcha", "verify you are human", "are you a human", "unusual traffic",
                "checking your browser", "security challenge", "cloudflare ray id",
                "cf-chl-", "hcaptcha", "recaptcha",
            )
            if any(marker in challenge_text for marker in captcha_markers):
                raise PageCheckError("CAPTCHA", "A CAPTCHA or anti-bot challenge was detected; it was not saved as a page change.")
            if response is not None and response.status in (403, 429):
                raise PageCheckError("BLOCKED", f"The website returned HTTP {response.status}; access may be blocked or rate-limited.")
            text = clean_text(html, include_selector, ignore_selector)
            if not text:
                raise PageCheckError("EMPTY PAGE", "No readable page text was found; the page may be unavailable or require interaction.")
            # Save a screenshot for comparison/history. It is moved into version history
            # by app.py when content hash changes.
            page.screenshot(path=screenshot_path, full_page=True, timeout=10000)
        except PlaywrightTimeoutError:
            raise PageCheckError("OUTAGE / TIMEOUT", "The website timed out while loading or capturing the page.")
        finally:
            browser.close()
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {"title": title, "text": text, "content_hash": content_hash, "screenshot_path": screenshot_path}
