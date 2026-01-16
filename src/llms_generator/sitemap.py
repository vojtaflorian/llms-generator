"""Sitemap parser for automatic URL discovery."""

import fnmatch

import defusedxml.ElementTree as ET
import requests
from rich.console import Console

console = Console()

# Sitemap XML namespace
SITEMAP_NS = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def parse_sitemap(sitemap_url: str, timeout: int = 30) -> list[str]:
    """Extract URLs from a sitemap.xml file.

    Supports both regular sitemaps and sitemap index files.

    Args:
        sitemap_url: URL to sitemap.xml
        timeout: Request timeout in seconds

    Returns:
        List of URLs found in the sitemap
    """
    console.print(f"  [cyan]Parsing sitemap: {sitemap_url}[/cyan]")

    response = requests.get(sitemap_url, timeout=timeout)
    response.raise_for_status()

    root = ET.fromstring(response.content)

    # Check if this is a sitemap index (contains other sitemaps)
    sitemap_locs = root.findall(".//ns:sitemap/ns:loc", SITEMAP_NS)
    if sitemap_locs:
        # Recursively parse all referenced sitemaps
        all_urls = []
        for loc in sitemap_locs:
            if loc.text:
                all_urls.extend(parse_sitemap(loc.text, timeout))
        return all_urls

    # Regular sitemap - extract URLs
    urls = []
    for url in root.findall(".//ns:url/ns:loc", SITEMAP_NS):
        if url.text:
            urls.append(url.text)

    console.print(f"  [dim]Found {len(urls)} URLs in sitemap[/dim]")
    return urls


def filter_urls(
    urls: list[str],
    include_pattern: str | None = None,
    exclude_pattern: str | None = None,
) -> list[str]:
    """Filter URLs using glob patterns.

    Supports multiple patterns separated by | (pipe).

    Args:
        urls: List of URLs to filter
        include_pattern: Glob pattern(s) for URLs to include (e.g., "**/docs/**|**/api/**")
        exclude_pattern: Glob pattern(s) for URLs to exclude (e.g., "**/blog/**|*banner*")

    Returns:
        Filtered list of URLs
    """
    result = urls

    if include_pattern:
        patterns = [p.strip() for p in include_pattern.split("|")]
        result = [u for u in result if any(fnmatch.fnmatch(u, p) for p in patterns)]

    if exclude_pattern:
        patterns = [p.strip() for p in exclude_pattern.split("|")]
        result = [u for u in result if not any(fnmatch.fnmatch(u, p) for p in patterns)]

    return result
