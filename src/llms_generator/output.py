"""Output generation for llms.txt files."""

import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

from .extractor import extract_with_ai, load_prompt
from .fetcher import fetch_page

load_dotenv()

console = Console()


def save_markdown(content: str, output_path: Path) -> None:
    """Save content to Markdown file.

    Args:
        content: Markdown content to save
        output_path: Destination file path
    """
    # Ensure directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Add generation timestamp as comment
    header = f"<!-- Generated: {datetime.now().isoformat()} -->\n\n"

    with open(output_path, "w") as f:
        f.write(header + content)

    console.print(f"  [green]Saved: {output_path}[/green]")


def generate_site_description(
    about_url: str,
    prompts_dir: Path,
    cache_dir: Path | None = None,
) -> str:
    """Generate site description from about page using AI.

    Args:
        about_url: URL to fetch and summarize (e.g., homepage or about page)
        prompts_dir: Directory containing prompt templates
        cache_dir: Optional cache directory

    Returns:
        Generated description string
    """
    try:
        console.print(f"[dim]Generating site description from: {about_url}[/dim]")
        _, text = fetch_page(about_url, cache_dir=cache_dir)

        # Truncate if too long
        if len(text) > 10000:
            text = text[:10000]

        # Load prompt from file
        prompt_template = load_prompt("site.txt", prompts_dir)
        description = extract_with_ai(text, prompt_template, dry_run=False, source_id="site_description")

        # Clean up response - remove quotes, extra whitespace
        description = description.strip().strip('"\'').strip()

        console.print(f"[dim]Generated description: {description}[/dim]")
        return description
    except Exception as e:
        console.print(f"[yellow]Warning: Could not generate site description: {e}[/yellow]")
        return ""


def generate_index(
    output_dir: Path,
    base_url: str = "",
    cache_dir: Path | None = None,
    prompts_dir: Path | None = None,
) -> str:
    """Generate main llms.txt index file.

    Args:
        output_dir: Directory containing llms/ subdirectory with .md files
        base_url: Base URL for links (e.g., https://example.com)
        cache_dir: Optional cache directory for fetching about page
        prompts_dir: Directory containing prompt templates

    Returns:
        Content of llms.txt
    """
    # Get site info from environment
    site_name = os.environ.get("SITE_NAME", "Website")
    site_description = os.environ.get("SITE_DESCRIPTION", "")
    site_about_url = os.environ.get("SITE_ABOUT_URL", "")

    # Auto-generate description if URL provided but no description
    if not site_description and site_about_url and prompts_dir:
        site_description = generate_site_description(site_about_url, prompts_dir, cache_dir)

    lines = [
        f"# {site_name}",
        "",
        "> This file provides AI-friendly information about this website.",
        "",
    ]

    # Add site description if available
    if site_description:
        lines.append(site_description)
        lines.append("")

    lines.extend([
        f"Generated: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "## Resources",
        "",
    ])

    # Find all .md files in llms/ subdirectory
    llms_dir = output_dir / "llms"
    if llms_dir.exists():
        md_files = sorted(llms_dir.glob("*.md"))
    else:
        # Fallback to root for backwards compatibility
        md_files = sorted(output_dir.glob("*.md"))

    for md_file in md_files:
        name = md_file.stem.replace("-", " ").replace("_", " ").title()

        if base_url:
            url = f"{base_url.rstrip('/')}/llms/{md_file.name}"
        else:
            url = f"llms/{md_file.name}"

        lines.append(f"- [{name}]({url})")

    # Add sitemap reference if configured
    sitemap_url = os.environ.get("SITE_SITEMAP_URL", "")
    if sitemap_url:
        lines.extend([
            "",
            "## Additional Resources",
            "",
            f"For a complete list of all pages, see the [sitemap]({sitemap_url}).",
        ])

    return "\n".join(lines)


def save_index(
    output_dir: Path,
    base_url: str = "",
    cache_dir: Path | None = None,
    prompts_dir: Path | None = None,
) -> None:
    """Generate and save llms.txt index file.

    Args:
        output_dir: Directory containing .md files
        base_url: Base URL for links
        cache_dir: Optional cache directory for fetching about page
        prompts_dir: Directory containing prompt templates
    """
    index_content = generate_index(output_dir, base_url, cache_dir, prompts_dir)
    index_path = output_dir / "llms.txt"

    with open(index_path, "w") as f:
        f.write(index_content)

    console.print(f"[green]Generated index: {index_path}[/green]")
