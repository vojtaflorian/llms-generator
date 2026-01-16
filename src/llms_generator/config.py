"""Configuration loader for sources.csv."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class Source:
    """Represents a single source configuration."""

    id: str
    url: str
    output: str
    chunk_method: str
    chunk_size: int
    prompt_file: str
    enabled: bool
    include_pattern: str | None = None
    exclude_pattern: str | None = None
    content_selector: str | None = None  # CSS selector for main content (e.g. ".product-detail")


def load_sources(csv_path: Path, only: list[str] | None = None) -> list[Source]:
    """Load sources from CSV file.

    Args:
        csv_path: Path to sources.csv
        only: Optional list of source IDs to filter

    Returns:
        List of Source objects
    """
    df = pd.read_csv(csv_path, comment="#")

    # Filter enabled sources
    df = df[df["enabled"] == True]  # noqa: E712

    # Filter by ID if specified
    if only:
        df = df[df["id"].isin(only)]

    sources = []
    for _, row in df.iterrows():
        # Handle optional columns
        include_pattern = row.get("include_pattern")
        exclude_pattern = row.get("exclude_pattern")
        content_selector = row.get("content_selector")

        sources.append(
            Source(
                id=row["id"],
                url=row["url"],
                output=row["output"],
                chunk_method=row["chunk_method"],
                chunk_size=int(row["chunk_size"]),
                prompt_file=row["prompt_file"],
                enabled=bool(row["enabled"]),
                include_pattern=include_pattern if pd.notna(include_pattern) else None,
                exclude_pattern=exclude_pattern if pd.notna(exclude_pattern) else None,
                content_selector=content_selector if pd.notna(content_selector) else None,
            )
        )

    return sources
