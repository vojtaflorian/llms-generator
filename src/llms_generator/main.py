"""Main CLI entry point for llms-generator."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .chunker import Chunk, create_chunks
from .config import load_sources
from .extractor import close_genai_client, extract_with_ai, load_prompt, merge_extractions
from .fetcher import fetch_page, set_rate_limit
from .output import save_index, save_markdown
from .usage import get_tracker, reset_tracker

console = Console()

# Parallel processing config
DEFAULT_MAX_WORKERS = 2
DEFAULT_BATCH_SIZE = 3
BATCH_DELAY = 2.0  # seconds between batches


def process_chunks_parallel(
    chunks: list[Chunk],
    prompt_template: str,
    dry_run: bool,
    source_id: str,
    max_workers: int = DEFAULT_MAX_WORKERS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    verbose: bool = False,
) -> list[str]:
    """Process chunks in parallel with batching for rate limiting.

    Args:
        chunks: List of chunks to process
        prompt_template: AI prompt template
        dry_run: Skip AI calls if True
        source_id: Source identifier for usage tracking
        max_workers: Max concurrent workers
        batch_size: Chunks per batch
        verbose: Print verbose output

    Returns:
        List of extraction results in original order
    """
    results = [None] * len(chunks)

    for batch_start in range(0, len(chunks), batch_size):
        batch_end = min(batch_start + batch_size, len(chunks))
        batch = [(i, chunks[i]) for i in range(batch_start, batch_end)]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    extract_with_ai,
                    chunk.content,
                    prompt_template,
                    dry_run,
                    source_id,
                ): idx
                for idx, chunk in batch
            }

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    if verbose:
                        console.print(f"  [red]Chunk {idx} failed: {e}[/red]")
                    results[idx] = f"# Error\n\nFailed to extract: {e}"

        # Rate limiting between batches
        if batch_end < len(chunks):
            time.sleep(BATCH_DELAY)

    return results


@click.command()
@click.option(
    "--sources",
    "-s",
    default="sources.csv",
    help="Path to sources CSV file",
    type=click.Path(exists=True),
)
@click.option(
    "--output",
    "-o",
    default="output",
    help="Output directory",
    type=click.Path(),
)
@click.option(
    "--only",
    help="Process only these source IDs (comma-separated)",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force re-fetch and re-generate (ignore cache)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Dry run - don't call AI, just show what would be processed",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Verbose output",
)
@click.option(
    "--base-url",
    default="",
    help="Base URL for llms.txt links (e.g., https://example.com)",
)
@click.option(
    "--parallel/--no-parallel",
    default=True,
    help="Enable/disable parallel chunk processing",
)
@click.option(
    "--workers",
    "-w",
    default=DEFAULT_MAX_WORKERS,
    help="Number of parallel workers",
    type=int,
)
@click.option(
    "--rate-limit",
    default=1.0,
    help="Delay between HTTP requests in seconds",
    type=float,
)
def cli(
    sources: str,
    output: str,
    only: str | None,
    force: bool,
    dry_run: bool,
    verbose: bool,
    base_url: str,
    parallel: bool,
    workers: int,
    rate_limit: float,
):
    """Generate llms.txt files from website sources.

    Reads configuration from sources.csv and generates Markdown files
    using AI extraction.
    """
    # Reset usage tracker for fresh run
    reset_tracker()

    console.print("[bold]LLMS.txt Generator[/bold]")
    console.print()

    # Configure rate limiting
    set_rate_limit(rate_limit)

    # Setup paths
    base_dir = Path.cwd()
    sources_path = Path(sources)
    output_dir = Path(output)
    cache_dir = base_dir / "cache"
    prompts_dir = base_dir / "prompts"

    # Show config in verbose mode
    if verbose:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        console.print("[dim]Configuration:[/dim]")
        console.print(f"  [dim]Project: {os.environ.get('GOOGLE_CLOUD_PROJECT', 'not set')}[/dim]")
        console.print(f"  [dim]Location: {os.environ.get('GOOGLE_CLOUD_LOCATION', 'europe-west1')}[/dim]")
        console.print(f"  [dim]Model: {os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash')}[/dim]")
        console.print(f"  [dim]Max content: {os.environ.get('MAX_CONTENT_LENGTH', '100000')} chars[/dim]")
        console.print(f"  [dim]Workers: {workers}, Rate limit: {rate_limit}s[/dim]")
        console.print()

    # Load sources
    only_list = only.split(",") if only else None
    source_list = load_sources(sources_path, only=only_list)

    if not source_list:
        console.print("[yellow]No enabled sources found in sources.csv[/yellow]")
        return

    console.print(f"Processing {len(source_list)} source(s)...")
    console.print()

    # Process each source
    for source in source_list:
        console.print(f"[bold cyan]→ {source.id}[/bold cyan] ({source.url})")

        try:
            # 1. Fetch page
            html, text = fetch_page(
                source.url,
                cache_dir=cache_dir if not force else None,
                force=force,
                content_selector=source.content_selector,
            )

            if verbose:
                console.print(f"  [dim]Fetched {len(text)} chars[/dim]")
                # Show content preview
                preview = text[:500].replace("\n", " ")[:200]
                console.print(f"  [dim]Preview: {preview}...[/dim]")
                if source.content_selector:
                    console.print(f"  [dim]Selector: {source.content_selector}[/dim]")

            # 2. Create chunks
            chunks = create_chunks(
                html=html,
                text=text,
                source_id=source.id,
                url=source.url,
                chunk_method=source.chunk_method,
                chunk_size=source.chunk_size,
                cache_dir=cache_dir,
                force=force,
                include_pattern=source.include_pattern,
                exclude_pattern=source.exclude_pattern,
                content_selector=source.content_selector,
            )

            console.print(f"  Created {len(chunks)} chunk(s)")

            # 3. Extract with AI
            prompt_template = load_prompt(source.prompt_file, prompts_dir)

            if parallel and len(chunks) > 1:
                console.print(f"  Extracting with {workers} workers...")
                extractions = process_chunks_parallel(
                    chunks=chunks,
                    prompt_template=prompt_template,
                    dry_run=dry_run,
                    source_id=source.id,
                    max_workers=workers,
                    verbose=verbose,
                )
            else:
                extractions = []
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                    transient=True,
                ) as progress:
                    task = progress.add_task("Extracting...", total=len(chunks))

                    for chunk in chunks:
                        if verbose:
                            console.print(f"  Processing chunk: {chunk.id}")

                        extraction = extract_with_ai(
                            content=chunk.content,
                            prompt_template=prompt_template,
                            dry_run=dry_run,
                            source_id=source.id,
                        )
                        extractions.append(extraction)
                        progress.advance(task)

            # 4. Merge and save to llms/ subdirectory
            merged = merge_extractions(extractions, source_id=source.id)
            output_path = output_dir / "llms" / source.output
            save_markdown(merged, output_path)

            # Show output preview in verbose mode
            if verbose:
                console.print(f"  [dim]Output size: {len(merged)} chars[/dim]")
                output_preview = merged[:300].replace("\n", " ")[:150]
                console.print(f"  [dim]Output preview: {output_preview}...[/dim]")

        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
            if verbose:
                import traceback

                traceback.print_exc()

        console.print()

    # Generate index
    console.print("[bold]Generating index...[/bold]")
    save_index(output_dir, base_url, cache_dir, prompts_dir)

    # Print usage summary (if not dry run)
    if not dry_run:
        tracker = get_tracker()
        tracker.print_summary()

    # Cleanup GenAI client resources
    close_genai_client()

    console.print()
    console.print("[bold green]Done![/bold green]")


if __name__ == "__main__":
    cli()
