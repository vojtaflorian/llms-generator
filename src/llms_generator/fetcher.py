"""Web page fetcher with caching and rate limiting support."""

import hashlib
import json
import time
from datetime import datetime
from functools import wraps
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from rich.console import Console

console = Console()

# Rate limiting state
_last_request_time = 0.0
_rate_limit_delay = 1.0  # seconds between requests


def set_rate_limit(delay: float) -> None:
    """Set the rate limit delay between requests."""
    global _rate_limit_delay
    _rate_limit_delay = delay


def rate_limited(func):
    """Decorator for rate limiting HTTP requests."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        global _last_request_time
        elapsed = time.time() - _last_request_time
        if elapsed < _rate_limit_delay and _last_request_time > 0:
            sleep_time = _rate_limit_delay - elapsed
            time.sleep(sleep_time)
        result = func(*args, **kwargs)
        _last_request_time = time.time()
        return result
    return wrapper

# Default headers to mimic a browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "cs,en;q=0.9",
}


def get_cache_path(url: str, cache_dir: Path) -> Path:
    """Generate cache file path for URL."""
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    return cache_dir / f"{url_hash}.json"


@rate_limited
def _fetch_url(url: str, timeout: int) -> requests.Response:
    """Internal function for fetching URL with rate limiting."""
    return requests.get(url, headers=HEADERS, timeout=timeout)


def fetch_page(
    url: str,
    cache_dir: Path | None = None,
    force: bool = False,
    timeout: int = 30,
    content_selector: str | None = None,
) -> tuple[str, str]:
    """Fetch a web page, optionally using cache.

    Args:
        url: URL to fetch
        cache_dir: Directory for caching (None to disable)
        force: Force re-fetch even if cached
        timeout: Request timeout in seconds
        content_selector: CSS selector for main content (e.g. ".product-detail", "#main")

    Returns:
        Tuple of (html_content, text_content)
    """
    # Generate cache key including selector
    cache_key = f"{url}:{content_selector}" if content_selector else url

    # Check cache first
    if cache_dir and not force:
        cache_path = get_cache_path(cache_key, cache_dir)
        if cache_path.exists():
            console.print(f"  [dim]Using cached: {url}[/dim]")
            with open(cache_path) as f:
                data = json.load(f)
                return data["html"], data["text"]

    # Fetch from web with rate limiting
    console.print(f"  [cyan]Fetching: {url}[/cyan]")
    response = _fetch_url(url, timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"

    html = response.text
    soup = BeautifulSoup(html, "lxml")

    # If content_selector is provided, extract only that element
    if content_selector:
        content_element = soup.select_one(content_selector)
        if content_element:
            # Remove script and style from selected element
            for tag in content_element(["script", "style"]):
                tag.decompose()
            text = content_element.get_text(separator="\n", strip=True)
            if not text:
                console.print(f"  [yellow]Warning: Selector '{content_selector}' found but empty[/yellow]")
        else:
            console.print(f"  [yellow]Warning: Selector '{content_selector}' not found, using full page[/yellow]")
            # Fallback to full page
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
    else:
        # Remove script and style elements from full page
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)

    # Save to cache
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = get_cache_path(cache_key, cache_dir)
        with open(cache_path, "w") as f:
            json.dump(
                {
                    "url": url,
                    "selector": content_selector,
                    "fetched_at": datetime.now().isoformat(),
                    "html": html,
                    "text": text,
                },
                f,
                ensure_ascii=False,
            )

    return html, text


def extract_links(html: str, base_url: str, selector: str | None = None) -> list[str]:
    """Extract links from HTML.

    Args:
        html: HTML content
        base_url: Base URL for resolving relative links
        selector: Optional CSS selector to limit scope

    Returns:
        List of absolute URLs
    """
    from urllib.parse import urljoin

    soup = BeautifulSoup(html, "lxml")
    container = soup.select_one(selector) if selector else soup

    links = []
    if container:
        for a in container.find_all("a", href=True):
            href = a["href"]
            absolute_url = urljoin(base_url, href)
            if absolute_url.startswith(("http://", "https://")):
                links.append(absolute_url)

    return list(dict.fromkeys(links))  # Remove duplicates while preserving order
