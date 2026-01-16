"""Chunking strategies for large pages."""

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup
from rich.console import Console

from .fetcher import extract_links, fetch_page
from .sitemap import filter_urls, parse_sitemap

console = Console()


@dataclass
class Chunk:
    """Represents a chunk of content to process."""

    id: str
    url: str
    content: str
    metadata: dict


def chunk_single(html: str, text: str, source_id: str, url: str) -> list[Chunk]:
    """No chunking - return entire page as single chunk."""
    return [
        Chunk(
            id=f"{source_id}_full",
            url=url,
            content=text,
            metadata={"type": "single"},
        )
    ]


def chunk_paginated(
    html: str,
    text: str,
    source_id: str,
    url: str,
    chunk_size: int,
    cache_dir=None,
    force: bool = False,
    content_selector: str | None = None,
) -> list[Chunk]:
    """Fetch all pages and create chunks.

    Looks for pagination patterns like ?page=N or /page/N
    """
    chunks = [
        Chunk(
            id=f"{source_id}_page1",
            url=url,
            content=text,
            metadata={"type": "paginated", "page": 1},
        )
    ]

    # Try to find pagination links
    soup = BeautifulSoup(html, "lxml")

    # Common pagination patterns
    pagination_selectors = [
        ".pagination a",
        ".pager a",
        '[class*="pagination"] a',
        '[class*="paging"] a',
        'a[href*="page="]',
        'a[href*="/page/"]',
    ]

    page_urls = set()
    for selector in pagination_selectors:
        for link in soup.select(selector):
            href = link.get("href", "")
            if href and ("page" in href.lower() or re.search(r"/\d+/?$", href)):
                from urllib.parse import urljoin

                abs_url = urljoin(url, href)
                if abs_url != url:
                    page_urls.add(abs_url)

    # Fetch additional pages
    for i, page_url in enumerate(sorted(page_urls)[:chunk_size - 1], start=2):
        try:
            _, page_text = fetch_page(
                page_url, cache_dir=cache_dir, force=force, content_selector=content_selector
            )
            chunks.append(
                Chunk(
                    id=f"{source_id}_page{i}",
                    url=page_url,
                    content=page_text,
                    metadata={"type": "paginated", "page": i},
                )
            )
        except Exception as e:
            console.print(f"  [yellow]Warning: Could not fetch {page_url}: {e}[/yellow]")

    return chunks


def chunk_alphabetical(
    html: str,
    text: str,
    source_id: str,
    url: str,
    chunk_size: int,
) -> list[Chunk]:
    """Split content alphabetically (for glossaries, dictionaries).

    Groups items by first letter into chunks.
    """
    # Split text into lines and try to identify alphabetical sections
    lines = text.split("\n")
    chunks = []

    current_chunk = []
    current_letters = []
    items_in_chunk = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if this line starts with a new letter (potential header)
        first_char = line[0].upper() if line else ""

        if first_char.isalpha():
            if items_in_chunk >= chunk_size and current_chunk:
                # Save current chunk
                letter_range = (
                    f"{current_letters[0]}-{current_letters[-1]}"
                    if len(current_letters) > 1
                    else current_letters[0]
                )
                chunks.append(
                    Chunk(
                        id=f"{source_id}_{letter_range}",
                        url=url,
                        content="\n".join(current_chunk),
                        metadata={"type": "alphabetical", "letters": letter_range},
                    )
                )
                current_chunk = []
                current_letters = []
                items_in_chunk = 0

            if first_char not in current_letters:
                current_letters.append(first_char)

        current_chunk.append(line)
        items_in_chunk += 1

    # Don't forget last chunk
    if current_chunk:
        letter_range = (
            f"{current_letters[0]}-{current_letters[-1]}"
            if len(current_letters) > 1
            else (current_letters[0] if current_letters else "misc")
        )
        chunks.append(
            Chunk(
                id=f"{source_id}_{letter_range}",
                url=url,
                content="\n".join(current_chunk),
                metadata={"type": "alphabetical", "letters": letter_range},
            )
        )

    return chunks if chunks else chunk_single(html, text, source_id, url)


def chunk_recursive(
    html: str,
    text: str,
    source_id: str,
    url: str,
    chunk_size: int,
    cache_dir=None,
    force: bool = False,
    max_depth: int = 2,
    content_selector: str | None = None,
    include_pattern: str | None = None,
    exclude_pattern: str | None = None,
) -> list[Chunk]:
    """Recursively crawl subpages (for category trees).

    Args:
        max_depth: Maximum depth to crawl
        content_selector: CSS selector for main content
        include_pattern: Glob pattern for URLs to include (e.g., "**/sluzby/**")
        exclude_pattern: Glob pattern for URLs to exclude
    """
    chunks = [
        Chunk(
            id=f"{source_id}_root",
            url=url,
            content=text,
            metadata={"type": "recursive", "depth": 0},
        )
    ]

    if max_depth < 1:
        return chunks

    # Find internal links on the page (use content_selector to limit to main content only)
    links = extract_links(html, url, selector=content_selector)

    # Filter to same-domain links
    from urllib.parse import urlparse

    base_domain = urlparse(url).netloc
    base_path = urlparse(url).path.rstrip("/")

    internal_links = [
        link for link in links if urlparse(link).netloc == base_domain and link != url
    ]

    # Apply URL path filtering
    if include_pattern or exclude_pattern:
        # Use glob patterns if specified
        internal_links = filter_urls(internal_links, include_pattern, exclude_pattern)
    elif not content_selector:
        # Default path filtering ONLY when no content_selector is set
        # (content_selector already limits link scope to main content area)
        internal_links = [
            link for link in internal_links
            if urlparse(link).path.startswith(base_path + "/")
            or urlparse(link).path == base_path
        ]
    # else: content_selector is set, trust it to limit which links are followed

    console.print(f"  [dim]Found {len(internal_links)} matching subpages[/dim]")

    # Limit number of subpages
    for link in internal_links[: chunk_size - 1]:
        try:
            sub_html, sub_text = fetch_page(
                link, cache_dir=cache_dir, force=force, content_selector=content_selector
            )
            chunks.append(
                Chunk(
                    id=f"{source_id}_{len(chunks)}",
                    url=link,
                    content=sub_text,
                    metadata={"type": "recursive", "depth": 1},
                )
            )
        except Exception as e:
            console.print(f"  [yellow]Warning: Could not fetch {link}: {e}[/yellow]")

    return chunks


def chunk_sitemap(
    sitemap_url: str,
    source_id: str,
    chunk_size: int,
    cache_dir=None,
    force: bool = False,
    include_pattern: str | None = None,
    exclude_pattern: str | None = None,
    content_selector: str | None = None,
) -> list[Chunk]:
    """Fetch all URLs from sitemap and create chunks.

    Args:
        sitemap_url: URL to sitemap.xml
        source_id: Unique source identifier
        chunk_size: Maximum number of URLs to process
        cache_dir: Cache directory path
        force: Force re-fetch
        include_pattern: Glob pattern for URLs to include
        exclude_pattern: Glob pattern for URLs to exclude
        content_selector: CSS selector for main content

    Returns:
        List of Chunk objects for each page in sitemap
    """
    # Parse sitemap
    urls = parse_sitemap(sitemap_url)

    # Apply glob filters
    urls = filter_urls(urls, include_pattern, exclude_pattern)

    # Limit number of URLs
    if chunk_size > 0:
        urls = urls[:chunk_size]

    console.print(f"  [dim]Processing {len(urls)} URLs from sitemap[/dim]")

    chunks = []
    for i, page_url in enumerate(urls):
        try:
            _, page_text = fetch_page(
                page_url, cache_dir=cache_dir, force=force, content_selector=content_selector
            )
            chunks.append(
                Chunk(
                    id=f"{source_id}_{i}",
                    url=page_url,
                    content=page_text,
                    metadata={"type": "sitemap", "index": i},
                )
            )
        except Exception as e:
            console.print(f"  [yellow]Warning: Could not fetch {page_url}: {e}[/yellow]")

    return chunks


def create_chunks(
    html: str,
    text: str,
    source_id: str,
    url: str,
    chunk_method: str,
    chunk_size: int,
    cache_dir=None,
    force: bool = False,
    include_pattern: str | None = None,
    exclude_pattern: str | None = None,
    content_selector: str | None = None,
) -> list[Chunk]:
    """Create chunks based on the specified method.

    Args:
        html: Raw HTML content
        text: Extracted text content
        source_id: Unique source identifier
        url: Source URL
        chunk_method: One of: single, paginated, alphabetical, recursive, sitemap
        chunk_size: Target chunk size
        cache_dir: Cache directory path
        force: Force re-fetch
        include_pattern: Glob pattern for URLs to include (recursive/sitemap)
        exclude_pattern: Glob pattern for URLs to exclude (recursive/sitemap)
        content_selector: CSS selector for main content

    Returns:
        List of Chunk objects
    """
    if chunk_method == "single":
        return chunk_single(html, text, source_id, url)
    elif chunk_method == "paginated":
        return chunk_paginated(
            html, text, source_id, url, chunk_size, cache_dir, force, content_selector
        )
    elif chunk_method == "alphabetical":
        return chunk_alphabetical(html, text, source_id, url, chunk_size)
    elif chunk_method == "recursive":
        return chunk_recursive(
            html, text, source_id, url, chunk_size, cache_dir, force,
            content_selector=content_selector,
            include_pattern=include_pattern,
            exclude_pattern=exclude_pattern,
        )
    elif chunk_method == "sitemap":
        return chunk_sitemap(
            url, source_id, chunk_size, cache_dir, force, include_pattern, exclude_pattern, content_selector
        )
    else:
        console.print(f"  [yellow]Unknown chunk method '{chunk_method}', using single[/yellow]")
        return chunk_single(html, text, source_id, url)
